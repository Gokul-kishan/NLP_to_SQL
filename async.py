numbers = [1, 2,4, 3, 4, 2, 5,4]
counts = {}

for num in numbers:
    counts[num] = counts.get(num, 0) + 1

print(counts)

# from typing import Annotated
# from pydantic import BaseModel, Field

# TargetAge = Annotated[int, Field(gt=20, lt= 30)]

# class User(BaseModel):
#     age:TargetAge

# class Customer(BaseModel):
#     age:TargetAge

# user = User(age=22)
# customer = Customer(age = 32)

# import asyncio

# # An async function with no await inside
# async def no_await_here():
#     print("This runs synchronously when executed!")
#     return 42

# async def main():
#     # Calling it returns a coroutine, it hasn't printed yet
#     coro = no_await_here() 
#     print("Coroutine created.",co)
#     print(f"called the function with await result: {await coro}")

#     # Actually executing it using await
#     # result = await coro 
#     # print(f"Result: {result}")

# asyncio.run(main())