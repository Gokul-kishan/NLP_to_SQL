import concurrent.futures
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_redis import RedisConfig, RedisVectorStore
from sentence_transformers import CrossEncoder

class UberRetrievalPipeline:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        # Models Initialization
        self.llm_rewriter = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Local High-Efficiency Cross-Encoder for Re-ranking
        self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        
        # Redis Dual Indices Setup
        self.few_shot_store = RedisVectorStore(
            embeddings=self.embeddings,
            config=RedisConfig(index_name="prompts_to_sql_bank", redis_url=redis_url, distance_metric="COSINE")
        )
        
        self.rules_store = RedisVectorStore(
            embeddings=self.embeddings,
            config=RedisConfig(index_name="business_rules_and_schemas", redis_url=redis_url, distance_metric="COSINE")
        )
        
        # Query Expansion Prompt Layout
        self.expansion_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert Data Engineer specializing in query expansion.\n"
                       "Given a user query and an Uber platform workspace, generate: \n"
                       "1. Two alternative ways to phrase the question using business terminology.\n"
                       "2. A 1-sentence hypothetical ideal database result or definition (HyDE approach).\n"
                       "Output each variation on a new line. Do not number them."),
            ("user", "Workspace: {workspace}\nQuery: {query}")
        ])

    def expand_query(self, query: str, workspace: str) -> List[str]:
        """Applies HyDE/Multi-Query expansion to break terminology barriers."""
        response = self.llm_rewriter.invoke(self.expansion_prompt.format(query=query, workspace=workspace))
        lines = [line.strip() for line in response.content.split("\n") if line.strip()]
        return [query] + lines

    def _fetch_index_chunks(self, store: RedisVectorStore, queries: List[str], workspace: str, k: int = 5) -> List[Document]:
        """Queries an isolated Redis index concurrently using parallel thread pools."""
        all_docs = []
        seen_ids = set()
        
        def search_single_query(q):
            return store.as_retriever(
                search_kwargs={"k": k, "filter": {"workspace": workspace}}
            ).invoke(q)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(search_single_query, queries)
            for doc_list in results:
                for doc in doc_list:
                    doc_id = doc.metadata.get("id") or hash(doc.page_content)
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        all_docs.append(doc)
        return all_docs

    def _rerank_documents(self, query: str, documents: List[Document], top_n: int = 3) -> str:
        """Uses a neural Cross-Encoder model to pick the top context segments."""
        if not documents:
            return "No relevant context found."
        pairs = [[query, doc.page_content] for doc in documents]
        scores = self.reranker.predict(pairs)
        scored_docs = sorted(zip(scores, documents), key=lambda x: x[0], reverse=True)
        top_docs = [doc for _, doc in scored_docs[:top_n]]
        return "\n\n---\n\n".join([d.page_content for d in top_docs])

    def retrieve_context(self, query: str, workspace: str) -> dict:
        """Executes full pipeline: Expansion, Parallel Index Fetching, and Cross-Encoder Re-ranking."""
        # 1. Query Expansion
        expanded_queries = self.expand_query(query, workspace)
        
        # 2. Parallel Vector Store Hits
        raw_few_shot_docs = self._fetch_index_chunks(self.few_shot_store, expanded_queries, workspace, k=4)
        raw_rules_docs = self._fetch_index_chunks(self.rules_store, expanded_queries, workspace, k=5)
        
        # 3. Cross-Encoder Sorting & Consolidation
        refined_few_shots = self._rerank_documents(query, raw_few_shot_docs, top_n=2)
        refined_rules = self._rerank_documents(query, raw_rules_docs, top_n=3)
        
        return {
            "few_shot_examples": refined_few_shots,
            "business_rules_context": refined_rules
        }
