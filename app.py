# imports:
from flask import Flask, jsonify, request
from flasgger import Swagger
from mongodb_connection_holder import MongoConnectionHolder
from routes import init_routes
from werkzeug.exceptions import HTTPException
import logging
import os

# Configure logging (environment-aware)
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# set app and swagger:
app = Flask(__name__)
Swagger(app)


# Global exception handlers
@app.errorhandler(404)
def not_found_error(e):
    """Handle 404 errors with JSON response."""
    return jsonify({'error': 'Not found', 'message': 'The requested resource was not found'}), 404


@app.errorhandler(405)
def method_not_allowed_error(e):
    """Handle 405 errors with JSON response."""
    return jsonify({'error': 'Method not allowed', 'message': 'This HTTP method is not allowed for this endpoint'}), 405


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all unhandled exceptions."""
    # Pass through HTTP exceptions (already handled by Flask)
    if isinstance(e, HTTPException):
        return jsonify({'error': e.name, 'message': e.description}), e.code

    # Log unexpected errors with full stack trace
    logger.exception(f"Unhandled exception: {type(e).__name__}: {e}")

    # Return generic error for unexpected exceptions
    return jsonify({'error': 'Internal server error', 'message': 'An unexpected error occurred'}), 500

# init DB connection:
MongoConnectionHolder.init()

# set routes:
init_routes(app)


# health check endpoint:
@app.route('/')
def health_check():
    """
    Health check endpoint with database connectivity verification
    ---
    responses:
        200:
            description: API is running and database is connected
        503:
            description: API is running but database is unavailable
    """
    try:
        db = MongoConnectionHolder.get_db()
        if db is None:
            logger.error("Health check failed: Database connection is None")
            return jsonify({'status': 'unhealthy', 'message': 'Database connection unavailable'}), 503

        # Ping the database to verify connectivity
        db.command('ping')
        return jsonify({'status': 'ok', 'message': 'Leaderboard API is running', 'database': 'connected'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return jsonify({'status': 'unhealthy', 'message': 'Database connection failed'}), 503


# run all:
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(port=port, host="0.0.0.0", debug=debug_mode)
