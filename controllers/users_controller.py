from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from utils.password_helper import hash_password, verify_password
from utils.jwt_helper import generate_token, require_auth
from datetime import datetime
import uuid
import re

users_blueprint = Blueprint('users', __name__)


def is_valid_email(email: str) -> bool:
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# 1. Register a new user
@users_blueprint.route('/users/register', methods=['POST'])
def register_user():
    """
    Register a new user account
    ---
    parameters:
        - name: user
          in: body
          required: true
          description: The user to register
          schema:
            id: UserRegister
            required:
                - email
                - password
                - username
            properties:
                email:
                    type: string
                    description: User's email address
                password:
                    type: string
                    description: User's password (min 8 characters)
                username:
                    type: string
                    description: User's display name
                avatar_url:
                    type: string
                    description: URL to the user's avatar image (optional)
    responses:
        201:
            description: User registered successfully
        400:
            description: Invalid input or email already exists
        500:
            description: Server error
    """
    data = request.json
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    # Validate required fields
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    if 'email' not in data or not data['email']:
        return jsonify({'error': 'Email is required'}), 400

    if 'password' not in data or not data['password']:
        return jsonify({'error': 'Password is required'}), 400

    if 'username' not in data or not data['username']:
        return jsonify({'error': 'Username is required'}), 400

    email = data['email'].lower().strip()
    password = data['password']
    username = data['username'].strip()

    # Validate email format
    if not is_valid_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    # Validate password length
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    # Check if email already exists
    users_collection = db['users']
    existing_user = users_collection.find_one({'email': email})
    if existing_user:
        return jsonify({'error': 'Email already registered'}), 409

    # Create user
    user_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    user_item = {
        "_id": user_id,
        "email": email,
        "password_hash": hash_password(password),
        "username": username,
        "avatar_url": data.get('avatar_url'),
        "created_at": now,
        "updated_at": now
    }

    users_collection.insert_one(user_item)

    # Generate token
    token = generate_token(user_id)

    # Return user without password_hash
    user_response = {
        "_id": user_item['_id'],
        "email": user_item['email'],
        "username": user_item['username'],
        "avatar_url": user_item['avatar_url'],
        "created_at": user_item['created_at']
    }

    return jsonify({
        'message': 'User registered successfully',
        'user': user_response,
        'token': token
    }), 201


# 2. Login
@users_blueprint.route('/users/login', methods=['POST'])
def login_user():
    """
    Login with email and password
    ---
    parameters:
        - name: credentials
          in: body
          required: true
          description: Login credentials
          schema:
            id: UserLogin
            required:
                - email
                - password
            properties:
                email:
                    type: string
                    description: User's email address
                password:
                    type: string
                    description: User's password
    responses:
        200:
            description: Login successful
        401:
            description: Invalid credentials
        500:
            description: Server error
    """
    data = request.json
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400

    email = data['email'].lower().strip()
    password = data['password']

    users_collection = db['users']
    user = users_collection.find_one({'email': email})

    if user is None:
        return jsonify({'error': 'Invalid email or password'}), 401

    if not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid email or password'}), 401

    # Generate token
    token = generate_token(user['_id'])

    # Return user without password_hash
    user_response = {
        "_id": user['_id'],
        "email": user['email'],
        "username": user['username'],
        "avatar_url": user.get('avatar_url'),
        "created_at": user['created_at']
    }

    return jsonify({
        'message': 'Login successful',
        'user': user_response,
        'token': token
    }), 200


# 3. Get current user profile
@users_blueprint.route('/users/me', methods=['GET'])
@require_auth
def get_current_user():
    """
    Get current user's profile
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
    responses:
        200:
            description: User profile
        401:
            description: Invalid or expired token
        404:
            description: User not found
        500:
            description: Server error
    """
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    users_collection = db['users']
    user = users_collection.find_one({'_id': request.user_id})

    if user is None:
        return jsonify({'error': 'User not found'}), 404

    # Return user without password_hash
    user_response = {
        "_id": user['_id'],
        "email": user['email'],
        "username": user['username'],
        "avatar_url": user.get('avatar_url'),
        "created_at": user['created_at'],
        "updated_at": user.get('updated_at')
    }

    return jsonify({'user': user_response}), 200


# 4. Update current user profile
@users_blueprint.route('/users/me', methods=['PUT'])
@require_auth
def update_current_user():
    """
    Update current user's profile
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
        - name: user
          in: body
          required: true
          description: Updated user data
          schema:
            id: UserUpdate
            properties:
                username:
                    type: string
                    description: New username
                avatar_url:
                    type: string
                    description: New avatar URL
    responses:
        200:
            description: User updated successfully
        401:
            description: Invalid or expired token
        500:
            description: Server error
    """
    data = request.json
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    users_collection = db['users']

    update_data = {'updated_at': datetime.now().isoformat()}
    if data and 'username' in data:
        update_data['username'] = data['username'].strip()
    if data and 'avatar_url' in data:
        update_data['avatar_url'] = data['avatar_url']

    users_collection.update_one(
        {'_id': request.user_id},
        {'$set': update_data}
    )

    updated_user = users_collection.find_one({'_id': request.user_id})

    user_response = {
        "_id": updated_user['_id'],
        "email": updated_user['email'],
        "username": updated_user['username'],
        "avatar_url": updated_user.get('avatar_url'),
        "created_at": updated_user['created_at'],
        "updated_at": updated_user.get('updated_at')
    }

    return jsonify({
        'message': 'User updated successfully',
        'user': user_response
    }), 200


# 5. Get all games the user has played (cross-game query)
@users_blueprint.route('/users/me/games', methods=['GET'])
@require_auth
def get_user_games():
    """
    Get all games the user has played
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
    responses:
        200:
            description: List of games with player info and scores
        401:
            description: Invalid or expired token
        500:
            description: Server error
    """
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    user_id = request.user_id

    # Get user
    users_collection = db['users']
    user = users_collection.find_one({'_id': user_id})
    if user is None:
        return jsonify({'error': 'User not found'}), 404

    # Find all players linked to this user
    players_collection = db['players']
    players = list(players_collection.find({'user_id': user_id}))

    # Get apps and scores for each player
    apps_collection = db['apps']
    scores_collection = db['scores']
    leaderboards_collection = db['leaderboards']

    games = []
    for player in players:
        app = apps_collection.find_one({'_id': player['app_id']})
        if app is None:
            continue

        # Get total scores for this player
        total_scores = scores_collection.count_documents({'player_id': player['_id']})

        # Get best scores (top 3 per leaderboard)
        best_scores = []

        # Find all leaderboards for this app
        leaderboards = list(leaderboards_collection.find({'app_id': player['app_id']}))

        for lb in leaderboards:
            # Get best score for this player on this leaderboard
            sort_order = -1 if lb.get('sort_order', 'desc') == 'desc' else 1
            best_score = scores_collection.find_one(
                {'player_id': player['_id'], 'leaderboard_id': lb['_id']},
                sort=[('score', sort_order)]
            )
            if best_score:
                best_scores.append({
                    'leaderboard': {
                        '_id': lb['_id'],
                        'name': lb['name']
                    },
                    'score': best_score['score'],
                    'created_at': best_score['created_at']
                })

        games.append({
            'app': {
                '_id': app['_id'],
                'name': app['name'],
                'created_at': app['created_at']
            },
            'player': {
                '_id': player['_id'],
                'username': player['username'],
                'avatar_url': player.get('avatar_url'),
                'linked_at': player.get('linked_at')
            },
            'total_scores': total_scores,
            'best_scores': best_scores
        })

    user_response = {
        "_id": user['_id'],
        "email": user['email'],
        "username": user['username'],
        "avatar_url": user.get('avatar_url')
    }

    return jsonify({
        'user': user_response,
        'games': games,
        'total_games': len(games)
    }), 200


# 6. Get all scores across all games (cross-game query)
@users_blueprint.route('/users/me/scores', methods=['GET'])
@require_auth
def get_user_scores():
    """
    Get all scores across all games
    ---
    parameters:
        - name: Authorization
          in: header
          type: string
          required: true
          description: Bearer token
        - name: limit
          in: query
          type: integer
          default: 50
          description: Maximum number of scores to return
    responses:
        200:
            description: List of all scores across games
        401:
            description: Invalid or expired token
        500:
            description: Server error
    """
    db = MongoConnectionHolder.get_db()

    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    user_id = request.user_id
    limit = request.args.get('limit', 50, type=int)
    limit = min(max(limit, 1), 100)  # Clamp between 1 and 100

    # Get user
    users_collection = db['users']
    user = users_collection.find_one({'_id': user_id})
    if user is None:
        return jsonify({'error': 'User not found'}), 404

    # Find all players linked to this user
    players_collection = db['players']
    players = list(players_collection.find({'user_id': user_id}))
    player_ids = [p['_id'] for p in players]
    player_map = {p['_id']: p for p in players}

    if not player_ids:
        return jsonify({
            'user': {
                "_id": user['_id'],
                "email": user['email'],
                "username": user['username'],
                "avatar_url": user.get('avatar_url')
            },
            'scores': [],
            'total_scores': 0
        }), 200

    # Get all scores for these players
    scores_collection = db['scores']
    apps_collection = db['apps']
    leaderboards_collection = db['leaderboards']

    scores = list(scores_collection.find(
        {'player_id': {'$in': player_ids}}
    ).sort('created_at', -1).limit(limit))

    total_scores = scores_collection.count_documents({'player_id': {'$in': player_ids}})

    # Enrich scores with app and leaderboard info
    enriched_scores = []
    for score in scores:
        player = player_map.get(score['player_id'])
        if player is None:
            continue

        leaderboard = leaderboards_collection.find_one({'_id': score['leaderboard_id']})
        app = apps_collection.find_one({'_id': player['app_id']})

        enriched_scores.append({
            'score': {
                '_id': score['_id'],
                'score': score['score'],
                'metadata': score.get('metadata'),
                'created_at': score['created_at']
            },
            'player': {
                '_id': player['_id'],
                'username': player['username']
            },
            'leaderboard': {
                '_id': leaderboard['_id'],
                'name': leaderboard['name']
            } if leaderboard else None,
            'app': {
                '_id': app['_id'],
                'name': app['name']
            } if app else None
        })

    user_response = {
        "_id": user['_id'],
        "email": user['email'],
        "username": user['username'],
        "avatar_url": user.get('avatar_url')
    }

    return jsonify({
        'user': user_response,
        'scores': enriched_scores,
        'total_scores': total_scores
    }), 200
