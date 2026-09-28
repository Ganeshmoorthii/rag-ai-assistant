import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    POSTGRES_URL: str = os.getenv("POSTGRES_URL", "")
    API_SECRET: str = os.getenv("API_SECRET", "")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"


settings = Settings()
