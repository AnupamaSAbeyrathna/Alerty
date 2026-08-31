from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Event(BaseModel):
    event_name: str
    event_time: str
    event_location: str
    event_description: str

@app.get("/")
def read_root():
    return {"message": "Welcome to FastAPI!"}

@app.get("/events")
def get_evemnts():
    return {"message": "List of events"}