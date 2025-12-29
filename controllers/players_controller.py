from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from controllers.apps_controller import validate_api_key
from utils.jwt_helper import verify_token, get_user_id_from_token
from datetime import datetime
import uuid

players_blueprint = Blueprint('players', __name__)


# 1. Register a new player
@players_blueprint.route('/players', methods=['POST'])
def register_player():
    """
    Register a new player
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: player
          in: body
          required: true
          description: The player to register
          schema:
            id: Player
            required:
                - username
            properties:
                username:
                    type: string
                    description: The player's username
                avatar_url:
                    type: string
                    description: URL to the player's avatar image (optional)
    responses:
        201:
            description: Player registered successfully
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

    if not data or 'username' not in data:
        return jsonify({'error': 'Username is required'}), 400

    # device_id is required for anonymous player tracking
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({'error': 'device_id is required'}), 400

    players_collection = db['players']

    # Check if a player with this device_id already exists for this app (idempotent)
    existing_player = players_collection.find_one({
        'app_id': app['_id'],
        'device_id': device_id
    })

    if existing_player:
        # Return existing player (idempotent registration)
        return jsonify({
            'message': 'Player already exists',
            'player': existing_player
        }), 200

    player_item = {
        "_id": str(uuid.uuid4()),
        "app_id": app['_id'],
        "device_id": device_id,
        "user_id": None,  # Anonymous player - no user linked yet
        "username": data['username'],
        "avatar_url": data.get('avatar_url', None),
        "created_at": datetime.now().isoformat(),
        "linked_at": None
    }

    players_collection.insert_one(player_item)

    return jsonify({
        'message': 'Player registered successfully',
        'player': player_item
    }), 201


# 2. Get player by ID
@players_blueprint.route('/players/<player_id>', methods=['GET'])
def get_player(player_id):
    """
    Get player information by ID
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: player_id
          in: path
          type: string
          required: true
          description: The player ID
    responses:
        200:
            description: Player information
        401:
            description: Invalid API key
        404:
            description: Player not found
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

    players_collection = db['players']
    player = players_collection.find_one({'_id': player_id, 'app_id': app['_id']})

    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify(player), 200


# 3. Get all players for an app
@players_blueprint.route('/players', methods=['GET'])
def get_all_players():
    """
    Get all players for the authenticated app
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
    responses:
        200:
            description: List of players
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

    players_collection = db['players']
    players = list(players_collection.find({'app_id': app['_id']}))

    return jsonify(players), 200


# 4. Update player
@players_blueprint.route('/players/<player_id>', methods=['PUT'])
def update_player(player_id):
    """
    Update player information
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: player_id
          in: path
          type: string
          required: true
          description: The player ID
        - name: player
          in: body
          required: true
          description: The updated player data
          schema:
            id: PlayerUpdate
            properties:
                username:
                    type: string
                    description: The player's new username
                avatar_url:
                    type: string
                    description: URL to the player's new avatar image
    responses:
        200:
            description: Player updated successfully
        401:
            description: Invalid API key
        404:
            description: Player not found
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

    players_collection = db['players']
    player = players_collection.find_one({'_id': player_id, 'app_id': app['_id']})

    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    # Update fields
    update_data = {}
    if 'username' in data:
        update_data['username'] = data['username']
    if 'avatar_url' in data:
        update_data['avatar_url'] = data['avatar_url']

    if update_data:
        players_collection.update_one(
            {'_id': player_id},
            {'$set': update_data}
        )

    updated_player = players_collection.find_one({'_id': player_id})
    return jsonify(updated_player), 200


# 5. Get player by device_id
@players_blueprint.route('/players/by-device/<device_id>', methods=['GET'])
def get_player_by_device(device_id):
    """
    Get player by device_id for a specific app
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: device_id
          in: path
          type: string
          required: true
          description: The device UUID
    responses:
        200:
            description: Player found
        401:
            description: Invalid API key
        404:
            description: Player not found for this device
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

    players_collection = db['players']
    player = players_collection.find_one({
        'app_id': app['_id'],
        'device_id': device_id
    })

    if player is None:
        return jsonify({'error': 'Player not found for this device'}), 404

    return jsonify({
        'player': player,
        'is_linked': player.get('user_id') is not None
    }), 200


# 6. Link player to user account
@players_blueprint.route('/players/<player_id>/link', methods=['POST'])
def link_player_to_user(player_id):
    """
    Link an anonymous player to a user account
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token for the user
        - name: player_id
          in: path
          type: string
          required: true
          description: The player ID to link
        - name: body
          in: body
          required: true
          description: Device verification
          schema:
            id: LinkPlayer
            required:
                - device_id
            properties:
                device_id:
                    type: string
                    description: Device ID for verification
    responses:
        200:
            description: Player linked successfully
        400:
            description: Player already linked to different user
        401:
            description: Invalid API key or token
        404:
            description: Player not found
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

    # Validate JWT token
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization header is required'}), 401

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return jsonify({'error': 'Invalid authorization header format'}), 401

    token = parts[1]
    user_id = get_user_id_from_token(token)

    if user_id is None:
        return jsonify({'error': 'Invalid or expired token'}), 401

    data = request.json
    if not data or 'device_id' not in data:
        return jsonify({'error': 'device_id is required for verification'}), 400

    device_id = data['device_id']

    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    players_collection = db['players']

    # Find the player
    player = players_collection.find_one({
        '_id': player_id,
        'app_id': app['_id']
    })

    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    # Verify device_id matches
    if player.get('device_id') != device_id:
        return jsonify({'error': 'Device ID does not match player'}), 400

    # Check if already linked to a different user
    if player.get('user_id') is not None and player['user_id'] != user_id:
        return jsonify({'error': 'Player already linked to a different user'}), 409

    # If already linked to this user, just return success
    if player.get('user_id') == user_id:
        return jsonify({
            'message': 'Player already linked to this user',
            'player': player
        }), 200

    # Link the player to the user
    now = datetime.now().isoformat()
    players_collection.update_one(
        {'_id': player_id},
        {'$set': {
            'user_id': user_id,
            'linked_at': now
        }}
    )

    updated_player = players_collection.find_one({'_id': player_id})

    return jsonify({
        'message': 'Player linked to user successfully',
        'player': updated_player
    }), 200


# 7. Get player by user_id for a specific app
@players_blueprint.route('/players/by-user', methods=['GET'])
def get_player_by_user():
    """
    Get player by user_id for a specific app
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token for the user
    responses:
        200:
            description: Player found
        401:
            description: Invalid API key or token
        404:
            description: No player linked to this user for this app
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

    # Validate JWT token
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization header is required'}), 401

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return jsonify({'error': 'Invalid authorization header format'}), 401

    token = parts[1]
    user_id = get_user_id_from_token(token)

    if user_id is None:
        return jsonify({'error': 'Invalid or expired token'}), 401

    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    players_collection = db['players']
    player = players_collection.find_one({
        'app_id': app['_id'],
        'user_id': user_id
    })

    if player is None:
        return jsonify({'error': 'No player linked to this user for this app'}), 404

    return jsonify({
        'player': player
    }), 200
