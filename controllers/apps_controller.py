from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from utils.jwt_helper import require_auth
from datetime import datetime
import uuid
import secrets
import logging

logger = logging.getLogger(__name__)

apps_blueprint = Blueprint('apps', __name__)


# 1. Register a new app and get API key (requires authentication)
@apps_blueprint.route('/apps', methods=['POST'])
@require_auth
def register_app():
    """
    Register a new app and receive an API key
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
        - name: app
          in: body
          required: true
          description: The app to register
          schema:
            id: App
            required:
                - name
            properties:
                name:
                    type: string
                    description: The name of the app/game
    responses:
        201:
            description: App registered successfully, returns app_id and api_key
        400:
            description: Invalid input
        401:
            description: Authorization required
        500:
            description: Server error
    """
    data = request.json
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    if not data or 'name' not in data:
        return jsonify({'error': 'App name is required'}), 400

    # Generate unique API key
    api_key = secrets.token_urlsafe(32)

    app_item = {
        "_id": str(uuid.uuid4()),
        "name": data['name'],
        "owner_id": request.user_id,  # Link app to authenticated user
        "api_key": api_key,
        "created_at": datetime.now().isoformat()
    }

    apps_collection = db['apps']
    apps_collection.insert_one(app_item)

    return jsonify({
        'message': 'App registered successfully',
        'app_id': app_item['_id'],
        'api_key': api_key
    }), 201


# 2. Get apps owned by current user
@apps_blueprint.route('/apps/mine', methods=['GET'])
@require_auth
def get_my_apps():
    """
    Get all apps owned by the authenticated user
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
    responses:
        200:
            description: List of apps owned by user
        401:
            description: Authorization required
        500:
            description: Server error
    """
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    apps_collection = db['apps']
    apps = list(apps_collection.find({'owner_id': request.user_id}))

    # Include API keys for owned apps
    apps_response = []
    for app in apps:
        apps_response.append({
            '_id': app['_id'],
            'name': app['name'],
            'api_key': app['api_key'],
            'created_at': app['created_at']
        })

    return jsonify({
        'apps': apps_response,
        'total': len(apps_response)
    }), 200


# 3. Get app info by ID
@apps_blueprint.route('/apps/<app_id>', methods=['GET'])
def get_app(app_id):
    """
    Get app information by ID
    ---
    parameters:
        - name: app_id
          in: path
          type: string
          required: true
          description: The app ID
    responses:
        200:
            description: App information
        404:
            description: App not found
        500:
            description: Server error
    """
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    apps_collection = db['apps']
    app = apps_collection.find_one({'_id': app_id})

    if app is None:
        return jsonify({'error': 'App not found'}), 404

    # Don't expose the API key in GET requests
    return jsonify({
        '_id': app['_id'],
        'name': app['name'],
        'created_at': app['created_at']
    }), 200


# 4. Delete an app (owner only)
@apps_blueprint.route('/apps/<app_id>', methods=['DELETE'])
@require_auth
def delete_app(app_id):
    """
    Delete an app owned by the authenticated user
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
        - name: app_id
          in: path
          type: string
          required: true
          description: The app ID
    responses:
        200:
            description: App deleted successfully
        401:
            description: Authorization required
        403:
            description: Not authorized to delete this app
        404:
            description: App not found
        500:
            description: Server error
    """
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    apps_collection = db['apps']
    app = apps_collection.find_one({'_id': app_id})

    if app is None:
        return jsonify({'error': 'App not found'}), 404

    # Check ownership
    if app.get('owner_id') != request.user_id:
        return jsonify({'error': 'Not authorized to delete this app'}), 403

    # Delete the app
    apps_collection.delete_one({'_id': app_id})

    # Also clean up related data (leaderboards, scores, players, trophies)
    db['leaderboards'].delete_many({'app_id': app_id})
    db['scores'].delete_many({'app_id': app_id})
    db['players'].delete_many({'app_id': app_id})
    db['trophies'].delete_many({'app_id': app_id})

    return jsonify({
        'message': 'App and all related data deleted successfully'
    }), 200


# 5. Validate API key (internal helper - can be used by other controllers)
def validate_api_key(api_key):
    """Validate an API key and return the app if valid."""
    if not api_key or not isinstance(api_key, str):
        return None

    db = MongoConnectionHolder.get_db()
    if db is None:
        return None

    try:
        apps_collection = db['apps']
        app = apps_collection.find_one({'api_key': api_key})
        return app
    except Exception as e:
        logger.error(f"Error validating API key: {e}", exc_info=True)
        return None


# 6. Get app by API key (for SDK initialization)
@apps_blueprint.route('/apps/validate', methods=['POST'])
def validate_app():
    """
    Validate an API key and return app info
    ---
    parameters:
        - name: api_key
          in: body
          required: true
          description: The API key to validate
          schema:
            id: ApiKey
            required:
                - api_key
            properties:
                api_key:
                    type: string
                    description: The API key
    responses:
        200:
            description: API key is valid, returns app info
        401:
            description: Invalid API key
        500:
            description: Server error
    """
    data = request.json
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    if not data or 'api_key' not in data:
        return jsonify({'error': 'API key is required'}), 400

    app = validate_api_key(data['api_key'])

    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    return jsonify({
        'valid': True,
        'app_id': app['_id'],
        'app_name': app['name']
    }), 200
