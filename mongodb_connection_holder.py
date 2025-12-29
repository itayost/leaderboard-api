from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os

# load environment variables:
load_dotenv()

DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
DB_NAME = os.getenv("DB_NAME")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")

MONGO_URI = f"mongodb+srv://{DB_USERNAME}:{DB_PASSWORD}@{DB_CONNECTION_STRING}/{DB_NAME}"


class MongoConnectionHolder:
    __db = None

    @staticmethod
    def init():
        if MongoConnectionHolder.__db is None:
            try:
                # create a new client and connect to server:
                client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

                # send a ping to confirm a successful connection:
                client.admin.command('ping')
                print("Pinged your deployment. You are successfully connected to the DB...")

                # set __db to be the connection's db:
                MongoConnectionHolder.__db = client[DB_NAME]
            except Exception as e:
                print(e)
        return MongoConnectionHolder.__db

    @staticmethod
    def get_db():
        if MongoConnectionHolder.__db is None:
            MongoConnectionHolder.init()

        return MongoConnectionHolder.__db
