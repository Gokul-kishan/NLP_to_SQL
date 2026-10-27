"""Uber text-to-SQL agent (LangGraph) with a human-in-the-loop context check.

Flow:
    START -> intent_router -> retrieval -> hitl_review -> sql_generator
          -> sql_validator -> sql_executor -> answer -> END
    (hitl_review can loop back to retrieval; validator/executor errors loop
     back to sql_generator up to MAX_RETRIES, then go to failure -> END)

Assumption: UberRetrievalPipeline.retrieve_context() returns a dict with
    few_shot_examples: str, business_rules_context: str, tables: list[str]
"""
import json
import os
import re
from functools import lru_cache
from typing import Annotated, Literal, Optional, TypedDict

import sqlglot
from sqlglot import expressions as exp
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from uber_retrieval_pipeline import UberRetrievalPipeline

# ==========================================
# 0. CONFIG
# ==========================================
DB_URL = os.getenv("DB_URL", "sqlite:///file:uber_mobility_data.db?mode=ro&uri=true")  # read-only
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")
SQL_DIALECT = os.getenv("SQL_DIALECT", "sqlite")

MAX_RETRIES = 2        # SQL repair attempts after the first try
MAX_HITL_ROUNDS = 2    # how many times a human may reject the retrieved context
MAX_ROWS = 200         # hard row cap on query results

Workspace = Literal["Mobility", "Marketplace", "Ads"]
WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)


# ==========================================
# 1. STATE
# ==========================================
class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # real conversation turns only
    user_query: str
    assigned_workspace: str
    retrieved_tables: list[str]
    human_tables: list[str]          # tables supplied by the human reviewer
    hitl_feedback: str
    hitl_rounds: int
    few_shot_examples: str
    business_rules_context: str
    schema_context: str
    generated_sql: str
    execution_result: str
    error: Optional[str]
    retry_count: int
    final_answer: str


# ==========================================
# 2. LAZY INFRASTRUCTURE (nothing connects at import time)
# ==========================================
@lru_cache(maxsize=1)
def get_engine():
    return create_engine(DB_URL)


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(model=MODEL_NAME, temperature=0)


@lru_cache(maxsize=1)
def get_pipeline() -> UberRetrievalPipeline:
    return UberRetrievalPipeline(redis_url=REDIS_URL)


# ==========================================
# 3. HELPERS
# ==========================================
class IntentOutput(BaseModel):
    workspace: Workspace


def extract_sql(raw: str) -> str:
    """Strip markdown fences and trailing semicolon once, at generation time."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.S | re.I)
    return (match.group(1) if match else raw).strip().rstrip(";")


def build_schema_context(tables: list[str]) -> str:
    inspector = inspect(get_engine())
    existing = set(inspector.get_table_names())
    blocks = []
    for table in tables:
        if table not in existing:
            blocks.append(f"-- {table}: NOT FOUND in database")
            continue
        cols = ", ".join(f"{c['name']} {c['type']}" for c in inspector.get_columns(table))
        blocks.append(f"{table}({cols})")
    return "\n".join(blocks)


def validate_sql(sql: str, allowed_tables: list[str]) -> Optional[str]:
    """Return an error message, or None if the SQL is a single safe SELECT on approved tables."""
    try:
        statements = sqlglot.parse(sql, read=SQL_DIALECT)
    except sqlglot.errors.ParseError as e:
        return f"SQL parse error: {e}"
    if len(statements) != 1 or statements[0] is None:
        return "Exactly one SQL statement is required."
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        return "Only read-only SELECT queries are permitted."
    if tree.find(*WRITE_NODES):
        return "Write/DDL operations are not permitted."

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used = {t.name.lower() for t in tree.find_all(exp.Table)} - cte_names
    unapproved = used - {t.lower() for t in allowed_tables}
    if unapproved:
        return f"Query uses tables outside the approved set: {sorted(unapproved)}"
    return None


def run_readonly_query(sql: str) -> str:
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql)).fetchmany(MAX_ROWS)
        return json.dumps([dict(r._mapping) for r in rows], default=str)


# ==========================================
# 4. NODES
# ==========================================
def intent_router(state: AgentState) -> dict:
    user_query = state["messages"][-1].content
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Classify the user query into exactly one workspace: Mobility, Marketplace, or Ads."),
        ("user", "{query}"),
    ])
    chain = prompt | get_llm().with_structured_output(IntentOutput)
    result = chain.invoke({"query": user_query})
    return {
        "user_query": user_query,
        "assigned_workspace": result.workspace,
        "retry_count": 0,
        "hitl_rounds": 0,
        "error": None,
    }


def retrieval(state: AgentState) -> dict:
    query = state["user_query"]
    if state.get("hitl_feedback"):
        query = f"{query}\nReviewer clarification: {state['hitl_feedback']}"

    retrieved = get_pipeline().retrieve_context(query=query, workspace=state["assigned_workspace"])
    tables = state.get("human_tables") or retrieved["tables"]  # human override wins
    return {
        "retrieved_tables": tables,
        "few_shot_examples": retrieved["few_shot_examples"],
        "business_rules_context": retrieved["business_rules_context"],
        "schema_context": build_schema_context(tables),
    }


def hitl_review(state: AgentState) -> Command[Literal["sql_generator", "retrieval", "failure"]]:
    """Pause so a human can confirm the workspace and tables before any SQL is written.

    Resume with one of:
        {"approved": True}
        {"approved": False, "workspace": "Ads", "tables": ["ads_spend"], "feedback": "..."}
    NOTE: on resume this node re-runs from the top, so keep it free of side effects.
    """
    decision = interrupt({
        "question": "Are the workspace and tables below correct for this request?",
        "user_query": state["user_query"],
        "workspace": state["assigned_workspace"],
        "tables": state["retrieved_tables"],
        "business_rules": state["business_rules_context"],
    })

    if decision.get("approved"):
        return Command(goto="sql_generator")

    rounds = state.get("hitl_rounds", 0) + 1
    if rounds > MAX_HITL_ROUNDS:
        return Command(
            update={"hitl_rounds": rounds, "error": "Reviewer rejected the retrieved context too many times."},
            goto="failure",
        )
    return Command(
        update={
            "assigned_workspace": decision.get("workspace") or state["assigned_workspace"],
            "human_tables": decision.get("tables") or [],
            "hitl_feedback": decision.get("feedback", ""),
            "hitl_rounds": rounds,
        },
        goto="retrieval",
    )


def sql_generator(state: AgentState) -> dict:
    error_context = ""
    if state.get("error"):
        error_context = (
            f"\n\n### PREVIOUS ATTEMPT FAILED\nSQL:\n{state.get('generated_sql', '')}\n"
            f"Error:\n{state['error']}\nFix the query."
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are Uber's SQL synthesis agent.\n\n"
         "### SCHEMA (use only these tables)\n{schema}\n\n"
         "### APPROVED EXAMPLES\n{examples}\n\n"
         "### BUSINESS RULES\n{rules}{error_context}\n\n"
         "Return ONE read-only SQL SELECT query inside a ```sql block. No explanation."),
        ("user", "{query}"),
    ])
    response = (prompt | get_llm()).invoke({
        "query": state["user_query"],
        "schema": state["schema_context"],
        "examples": state["few_shot_examples"],
        "rules": state["business_rules_context"],
        "error_context": error_context,
    })
    return {"generated_sql": extract_sql(response.content)}


def sql_validator(state: AgentState) -> dict:
    error = validate_sql(state["generated_sql"], state["retrieved_tables"])
    if error:
        return {"error": error, "retry_count": state["retry_count"] + 1}
    return {"error": None}


def sql_executor(state: AgentState) -> dict:
    try:
        return {"execution_result": run_readonly_query(state["generated_sql"]), "error": None}
    except SQLAlchemyError as e:
        return {"error": f"Database execution error: {e}", "retry_count": state["retry_count"] + 1}


def answer(state: AgentState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Answer the user's question using ONLY the query results (JSON rows) below. "
         "If the result is empty, say no matching data was found. Be concise.\n\n"
         "SQL used:\n{sql}\n\nResults:\n{results}"),
        ("user", "{query}"),
    ])
    response = (prompt | get_llm()).invoke({
        "sql": state["generated_sql"],
        "results": state["execution_result"],
        "query": state["user_query"],
    })
    return {"final_answer": response.content, "messages": [AIMessage(content=response.content)]}


def failure(state: AgentState) -> dict:
    msg = f"Sorry, I couldn't answer this request. Reason: {state.get('error', 'unknown error')}"
    return {"final_answer": msg, "messages": [AIMessage(content=msg)]}


# ==========================================
# 5. ROUTING + GRAPH
# ==========================================
def route_on_error(success_node: str):
    def router(state: AgentState) -> str:
        if not state.get("error"):
            return success_node
        return "sql_generator" if state["retry_count"] <= MAX_RETRIES else "failure"
    return router


def build_graph(checkpointer):
    g = StateGraph(AgentState)
    g.add_node("intent_router", intent_router)
    g.add_node("retrieval", retrieval)
    g.add_node("hitl_review", hitl_review)
    g.add_node("sql_generator", sql_generator)
    g.add_node("sql_validator", sql_validator)
    g.add_node("sql_executor", sql_executor)
    g.add_node("answer", answer)
    g.add_node("failure", failure)

    g.add_edge(START, "intent_router")
    g.add_edge("intent_router", "retrieval")
    g.add_edge("retrieval", "hitl_review")      # hitl_review routes itself via Command
    g.add_edge("sql_generator", "sql_validator")
    g.add_conditional_edges("sql_validator", route_on_error("sql_executor"),
                            ["sql_executor", "sql_generator", "failure"])
    g.add_conditional_edges("sql_executor", route_on_error("answer"),
                            ["answer", "sql_generator", "failure"])
    g.add_edge("answer", END)
    g.add_edge("failure", END)
    return g.compile(checkpointer=checkpointer)


# ==========================================
# 6. USAGE
# ==========================================
if __name__ == "__main__":
    with RedisSaver.from_conn_string(REDIS_URL) as saver:
        saver.setup()
        app = build_graph(saver)
        config = {"configurable": {"thread_id": "session-001"}}  # required for checkpointing/resume

        result = app.invoke({"messages": [HumanMessage(content="Total completed trips per city last week?")]}, config)

        # Graph pauses at hitl_review; show the human what was retrieved
        if "__interrupt__" in result:
            print("REVIEW REQUEST:", result["__interrupt__"][0].value)
            # Approve as-is, or reject with corrections:
            #   Command(resume={"approved": False, "workspace": "Mobility", "tables": ["trips"], "feedback": "..."})
            result = app.invoke(Command(resume={"approved": True}), config)

        print(result["final_answer"])

# import os
# import operator
# from typing import TypedDict, Annotated, Sequence
# from sqlalchemy import create_engine, text

# from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_core.tools import tool
# from langchain_openai import ChatOpenAI

# from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.redis import RedisSaver

# # Import the decoupled pipeline component
# from uber_retrieval_pipeline import UberRetrievalPipeline

# # ==========================================
# # 1. GRAPH STATE DEFINITION
# # ==========================================
# class UberAgentState(TypedDict):
#     messages: Annotated[Sequence[BaseMessage], operator.add]
#     assigned_workspace: str       # E.g., 'Mobility', 'Marketplace', 'Ads'
#     few_shot_examples: str        # Managed by external pipeline
#     business_rules_context: str   # Managed by external pipeline
#     generated_sql: str
#     execution_raw_data: str
#     retry_count: int

# # ==========================================
# # 2. REUSABLE INFRASTRUCTURE & ENGINES
# # ==========================================
# db_engine = create_engine("sqlite:///uber_mobility_data.db")
# llm_agent = ChatOpenAI(model="gpt-4o", temperature=0)

# # Instantiate the pipeline service globally or lazily inside the node
# retrieval_pipeline = UberRetrievalPipeline(redis_url="redis://localhost:6379/0")

# @tool
# def execute_sql_query(query: str) -> str:
#     """Safely processes and executes the generated queries against SQL Engine."""
#     clean_query = query.strip().replace("```sql", "").replace("```", "")
#     forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
#     if any(word in clean_query.upper() for word in forbidden):
#         return "Error: Security constraint violation. Read-only operations permitted."
#     try:
#         with db_engine.connect() as connection:
#             result = connection.execute(text(clean_query))
#             return str([dict(row._mapping) for row in result.fetchall()])[:4000]
#     except Exception as e:
#         return f"Database Execution Error: {str(e)}"

# # ==========================================
# # 3. GRAPH NODES (AGENT WORKERS)
# # ==========================================
# def intent_agent(state: UberAgentState):
#     user_query = state["messages"][-1].content
#     intent_prompt = ChatPromptTemplate.from_messages([
#         ("system", "You are the Uber Intent Routing Gateway. Classify the user query into a specialized System Workspace. Available Workspaces: [Mobility, Marketplace, Ads]. Return ONLY the single workspace name."),
#         ("user", "{query}")
#     ])
#     workspace = (intent_prompt | llm_agent).invoke({"query": user_query}).content.strip()
#     return {
#         "messages": [AIMessage(content=f"[Intent Agent]: Routed request to the {workspace} workspace.")],
#         "assigned_workspace": workspace,
#         "retry_count": 0
#     }

# def dual_index_retrieval_node(state: UberAgentState):
#     """LangGraph structural node wrapper that delegates complex search out to our dedicated pipeline file."""
#     user_query = state["messages"][-2].content if len(state["messages"]) > 1 else state["messages"][-1].content
#     workspace = state["assigned_workspace"]
    
#     # Delegate execution directly to the pipeline layer class
#     retrieved_data = retrieval_pipeline.retrieve_context(query=user_query, workspace=workspace)
    
#     return {
#         "few_shot_examples": retrieved_data["few_shot_examples"],
#         "business_rules_context": retrieved_data["business_rules_context"]
#     }

# def sql_generator_agent(state: UberAgentState):
#     user_query = state["messages"][-3].content if len(state["messages"]) > 2 else state["messages"][-1].content
#     examples = state["few_shot_examples"]
#     rules = state["business_rules_context"]
    
#     error_context = ""
#     if "messages" in state and len(state["messages"]) > 0 and "[Executor Critic]" in state["messages"][-1].content:
#         error_context = f"\n\n### CRITICAL PREVIOUS RUNTIME ERROR:\nYour last query failed with this error:\n{state['execution_raw_data']}\nModify syntax based on business rules to fix."

#     generator_prompt = ChatPromptTemplate.from_messages([
#         ("system", "You are Uber's Core SQL Synthesis Agent.\n\n"
#                    "### PART I: APPROVED WORKSPACE EXAMPLES\n{examples}\n\n"
#                    "### PART II: DATA TARGET RULES & BOUNDS\n{rules}{error_context}\n\n"
#                    "Generate an optimized SQL query matching the request. Return ONLY valid executable SQL inside standard markdown blocks."),
#         ("user", "{query}")
#     ])
    
#     response = (generator_prompt | llm_agent).invoke({
#         "query": user_query, 
#         "examples": examples, 
#         "rules": rules, 
#         "error_context": error_context
#     })
#     return {
#         "messages": [AIMessage(content="[SQL Generator]: Generated query candidate architecture.")],
#         "generated_sql": response.content
#     }

# def sql_reviewer_executor_agent(state: UberAgentState):
#     candidate_sql = state["generated_sql"]
#     execution_result = execute_sql_query.invoke({"query": candidate_sql})
    
#     if "Execution Error" in execution_result:
#         return {
#             "messages": [AIMessage(content=f"[Executor Critic]: Runtime failure detected: {execution_result}")],
#             "execution_raw_data": execution_result
#         }
#     return {
#         "messages": [AIMessage(content=f"[Executor Critic]: Execution Succeeded. Raw results:\n{execution_result}")],
#         "execution_raw_data": execution_result
#     }

# # ==========================================
# # 4. CONDITIONAL ROUTING AND WORKFLOW ENGINE
# # ==========================================
# def evaluate_execution_loop(state: UberAgentState):
#     if "Execution Error" in state["execution_raw_data"] and state["retry_count"] < 2:
#         state["retry_count"] += 1
#         return "re_evaluate_generation"
#     return END

# # Set up Redis State Saver Engine
# redis_saver = RedisSaver.from_conn_info(host="localhost", port=6379, db=0)

# workflow = StateGraph(UberAgentState)

# # Append Graph Steps
# workflow.add_node("intent_router", intent_agent)
# workflow.add_node("dual_rag_engine", dual_index_retrieval_node)
# workflow.add_node("sql_synthesizer", sql_generator_agent)
# workflow.add_node("executor_critic", sql_reviewer_executor_agent)

# # Set Static Directed Transitions
# workflow.add_edge(START, "intent_router")
# workflow.add_edge("intent_router", "dual_rag_engine")
# workflow.add_edge("dual_rag_engine", "sql_synthesizer")
# workflow.add_edge("sql_synthesizer", "executor_critic")

# # Set Conditional Healing Transitions
# workflow.add_conditional_edges(
#     "executor_critic",
#     evaluate_execution_loop,
#     {
#         "re_evaluate_generation": "sql_synthesizer",
#         END: END
#     }
# )

# app = workflow.compile(checkpointer=redis_saver)
