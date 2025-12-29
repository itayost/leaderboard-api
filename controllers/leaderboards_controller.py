from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from controllers.apps_controller import validate_api_key
from datetime import datetime
import uuid

leaderboards_blueprint = Blueprint('leaderboards', __name__)


# 1. Create a new leaderboard
@leaderboards_blueprint.route('/leaderboards', methods=['POST'])
def create_leaderboard():
    """
    Create a new leaderboard
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: leaderboard
          in: body
          required: true
          description: The leaderboard to create
          schema:
            id: Leaderboard
            required:
                - name
            properties:
                name:
                    type: string
                    description: The name of the leaderboard (e.g., "Daily High Scores")
                sort_order:
                    type: string
                    description: Sort order - "desc" for highest first (default), "asc" for lowest first
    responses:
        201:
            description: Leaderboard created successfully
        400:
            description: Invalid input
        401:
            description: Invalid API key
        500:
            description: Server error
    """
    # Validate API key
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    data = request.json
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    if not data or 'name' not in data:
        return jsonify({'error': 'Leaderboard name is required'}), 400

    # Validate sort_order
    sort_order = data.get('sort_order', 'desc')
    if sort_order not in ['asc', 'desc']:
        return jsonify({'error': 'sort_order must be "asc" or "desc"'}), 400

    leaderboards_collection = db['leaderboards']

    # Check for duplicate name within the same app
    existing = leaderboards_collection.find_one({
        'app_id': app['_id'],
        'name': data['name']
    })
    if existing:
        return jsonify({'error': 'A leaderboard with this name already exists'}), 409

    leaderboard_item = {
        "_id": str(uuid.uuid4()),
        "app_id": app['_id'],
        "name": data['name'],
        "sort_order": sort_order,
        "created_at": datetime.now().isoformat()
    }

    leaderboards_collection.insert_one(leaderboard_item)

    return jsonify({
        'message': 'Leaderboard created successfully',
        'leaderboard': leaderboard_item
    }), 201


# 2. Get all leaderboards for an app
@leaderboards_blueprint.route('/leaderboards', methods=['GET'])
def get_leaderboards():
    """
    Get all leaderboards for the authenticated app
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
    responses:
        200:
            description: List of leaderboards
        401:
            description: Invalid API key
        500:
            description: Server error
    """
    # Validate API key
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    leaderboards_collection = db['leaderboards']
    leaderboards = list(leaderboards_collection.find({'app_id': app['_id']}))

    return jsonify(leaderboards), 200


# 3. Get leaderboard by ID
@leaderboards_blueprint.route('/leaderboards/<leaderboard_id>', methods=['GET'])
def get_leaderboard(leaderboard_id):
    """
    Get leaderboard information by ID
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: leaderboard_id
          in: path
          type: string
          required: true
          description: The leaderboard ID
    responses:
        200:
            description: Leaderboard information
        401:
            description: Invalid API key
        404:
            description: Leaderboard not found
        500:
            description: Server error
    """
    # Validate API key
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    leaderboards_collection = db['leaderboards']
    leaderboard = leaderboards_collection.find_one({
        '_id': leaderboard_id,
        'app_id': app['_id']
    })

    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    return jsonify(leaderboard), 200


# 4. Delete leaderboard
@leaderboards_blueprint.route('/leaderboards/<leaderboard_id>', methods=['DELETE'])
def delete_leaderboard(leaderboard_id):
    """
    Delete a leaderboard and all its scores
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: leaderboard_id
          in: path
          type: string
          required: true
          description: The leaderboard ID
    responses:
        200:
            description: Leaderboard deleted successfully
        401:
            description: Invalid API key
        404:
            description: Leaderboard not found
        500:
            description: Server error
    """
    # Validate API key
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    leaderboards_collection = db['leaderboards']
    leaderboard = leaderboards_collection.find_one({
        '_id': leaderboard_id,
        'app_id': app['_id']
    })

    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    # Delete all scores for this leaderboard
    scores_collection = db['scores']
    scores_collection.delete_many({'leaderboard_id': leaderboard_id})

    # Delete the leaderboard
    leaderboards_collection.delete_one({'_id': leaderboard_id})

    return jsonify({'message': 'Leaderboard and all scores deleted successfully'}), 200
