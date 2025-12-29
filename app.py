# imports:
from flask import Flask
from flasgger import Swagger
from mongodb_connection_holder import MongoConnectionHolder
from routes import init_routes
import os

# set app and swagger:
app = Flask(__name__)
Swagger(app)

# init DB connection:
MongoConnectionHolder.init()

# set routes:
init_routes(app)


# health check endpoint:
@app.route('/')
def health_check():
    """
    Health check endpoint
    ---
    responses:
        200:
            description: API is running
    """
    return {'status': 'ok', 'message': 'Leaderboard API is running'}


# run all:
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(port=port, host="0.0.0.0", debug=True)
