from pydantic import BaseModel

class SessionRequest(BaseModel):
    user_id: str
    challenge_id: str

class SessionResponse(BaseModel):
    status: str
    message: str
