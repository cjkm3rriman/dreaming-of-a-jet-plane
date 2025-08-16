from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/")
async def read_root(request: Request):
    client_ip = request.client.host
    return {"client_ip": client_ip}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)