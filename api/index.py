from fastapi import FastAPI
from fastapi import Query
app = FastAPI()

# @app.get("/root")
# async def root(name:str = Query(...)):
#     answer = {"message": "Hello FastAPI!"}
#     print(f'1.給予資料:{answer}')
#     print(f"2.收到回傳結果:{name}")
#     return {"message": "Hello FastAPI!"}

@app.get("/page")
async def root():

    return "Success!!"


@app.post("/root_post3")
async def root_post(name:str = Query(...)):
    res = {"message": "OK123"}
    print(f"1.收到結果:{name}")
    print(f"2.回傳結果:{res}")

    return {"message": "OK123"}


# if __name__ == "__main__":
#     uvicorn app:app --host 0.0.0.0 --port 5000 --reloaduvicorn app:app --host 0.0.0.0 --port 5000 --reload
#     uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
