import subprocess

from fastapi import Depends, FastAPI, Query

from .service import UserService

app = FastAPI()


def get_current_user():
    return "user"


@app.get("/users/{user_id}")
def read_user(user_id: str, q: str = Query(""), user=Depends(get_current_user)):
    service = UserService()
    subprocess.run(["echo", q])
    return service.find(user_id)
