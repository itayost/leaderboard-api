from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from controllers.apps_controller import validate_api_key
from datetime import datetime
import uuid

scores_blueprint = Blueprint('scores', __name__)


def get_leaderboard_sort_order(db, leaderboard_id):
    """Helper to get the sort order for a leaderboard"""
    leaderboards_collection = db['leaderboards']
    leaderboard = leaderboards_collection.find_one({'_id': leaderboard_id})
    if leaderboard:
        return -1 if leaderboard.get('sort_order', 'desc') == 'desc' else 1
    return -1  # default to descending


# 1. Submit a score
@scores_blueprint.route('/scores', methods=['POST'])
def submit_score():
    """
    Submit a new score
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: score
          in: body
          required: true
          description: The score to submit
          schema:
            id: Score
            required:
                - leaderboard_id
                - player_id
                - score
            properties:
                leaderboard_id:
                    type: string
                    description: The leaderboard ID
                player_id:
                    type: string
                    description: The player ID
                score:
                    type: integer
                    description: The score value
                metadata:
                    type: object
                    description: Optional metadata (e.g., level, time, etc.)
    responses:
        201:
            description: Score submitted successfully
        400:
            description: Invalid input
        401:
            description: Invalid API key
        404:
            description: Leaderboard or player not found
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

    # Validate required fields
    if not data or not all(key in data for key in ['leaderboard_id', 'player_id', 'score']):
        return jsonify({'error': 'leaderboard_id, player_id, and score are required'}), 400

    # Verify leaderboard exists and belongs to this app
    leaderboards_collection = db['leaderboards']
    leaderboard = leaderboards_collection.find_one({
        '_id': data['leaderboard_id'],
        'app_id': app['_id']
    })
    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    # Verify player exists and belongs to this app
    players_collection = db['players']
    player = players_collection.find_one({
        '_id': data['player_id'],
        'app_id': app['_id']
    })
    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    score_item = {
        "_id": str(uuid.uuid4()),
        "leaderboard_id": data['leaderboard_id'],
        "player_id": data['player_id'],
        "score": data['score'],
        "metadata": data.get('metadata', {}),
        "created_at": datetime.now().isoformat()
    }

    scores_collection = db['scores']
    scores_collection.insert_one(score_item)

    return jsonify({
        'message': 'Score submitted successfully',
        'score': score_item
    }), 201


# 2. Get top scores for a leaderboard
@scores_blueprint.route('/scores/<leaderboard_id>', methods=['GET'])
def get_top_scores(leaderboard_id):
    """
    Get top scores for a leaderboard
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
        - name: limit
          in: query
          type: integer
          required: false
          default: 10
          description: Number of top scores to return (max 100)
    responses:
        200:
            description: List of top scores with player info
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

    # Verify leaderboard exists
    leaderboards_collection = db['leaderboards']
    leaderboard = leaderboards_collection.find_one({
        '_id': leaderboard_id,
        'app_id': app['_id']
    })
    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    # Get limit parameter
    limit = min(int(request.args.get('limit', 10)), 100)

    # Get sort order
    sort_direction = get_leaderboard_sort_order(db, leaderboard_id)

    # Get top scores
    scores_collection = db['scores']
    players_collection = db['players']

    top_scores = list(scores_collection.find(
        {'leaderboard_id': leaderboard_id}
    ).sort('score', sort_direction).limit(limit))

    # Enrich with player info and add rank
    result = []
    for idx, score in enumerate(top_scores):
        player = players_collection.find_one({'_id': score['player_id']})
        result.append({
            'rank': idx + 1,
            'score': score,
            'player': player
        })

    return jsonify({
        'leaderboard': leaderboard,
        'total_scores': scores_collection.count_documents({'leaderboard_id': leaderboard_id}),
        'scores': result
    }), 200


# 3. Get player's rank and nearby scores
@scores_blueprint.route('/scores/<leaderboard_id>/player/<player_id>', methods=['GET'])
def get_player_rank(leaderboard_id, player_id):
    """
    Get player's rank and nearby scores
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
        - name: player_id
          in: path
          type: string
          required: true
          description: The player ID
        - name: nearby
          in: query
          type: integer
          required: false
          default: 5
          description: Number of nearby players to include above and below
    responses:
        200:
            description: Player's rank and nearby scores
        401:
            description: Invalid API key
        404:
            description: Leaderboard, player, or score not found
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

    # Verify leaderboard exists
    leaderboards_collection = db['leaderboards']
    leaderboard = leaderboards_collection.find_one({
        '_id': leaderboard_id,
        'app_id': app['_id']
    })
    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    # Verify player exists
    players_collection = db['players']
    player = players_collection.find_one({
        '_id': player_id,
        'app_id': app['_id']
    })
    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    # Get nearby parameter
    nearby = min(int(request.args.get('nearby', 5)), 20)

    scores_collection = db['scores']
    sort_direction = get_leaderboard_sort_order(db, leaderboard_id)

    # Get the player's best score
    player_scores = list(scores_collection.find({
        'leaderboard_id': leaderboard_id,
        'player_id': player_id
    }).sort('score', sort_direction).limit(1))

    if not player_scores:
        return jsonify({'error': 'Player has no scores on this leaderboard'}), 404

    player_best_score = player_scores[0]

    # Calculate rank by counting scores better than player's best
    if sort_direction == -1:  # desc - higher is better
        better_scores_count = scores_collection.count_documents({
            'leaderboard_id': leaderboard_id,
            'score': {'$gt': player_best_score['score']}
        })
    else:  # asc - lower is better
        better_scores_count = scores_collection.count_documents({
            'leaderboard_id': leaderboard_id,
            'score': {'$lt': player_best_score['score']}
        })

    player_rank = better_scores_count + 1
    total_players = len(scores_collection.distinct('player_id', {'leaderboard_id': leaderboard_id}))

    # Get nearby scores
    all_scores_sorted = list(scores_collection.find(
        {'leaderboard_id': leaderboard_id}
    ).sort('score', sort_direction))

    # Find player's position in the sorted list
    player_position = None
    for idx, score in enumerate(all_scores_sorted):
        if score['player_id'] == player_id:
            player_position = idx
            break

    # Get nearby scores
    start_idx = max(0, player_position - nearby)
    end_idx = min(len(all_scores_sorted), player_position + nearby + 1)
    nearby_scores = all_scores_sorted[start_idx:end_idx]

    # Enrich with player info and rank
    nearby_result = []
    for idx, score in enumerate(nearby_scores):
        p = players_collection.find_one({'_id': score['player_id']})
        nearby_result.append({
            'rank': start_idx + idx + 1,
            'score': score,
            'player': p
        })

    return jsonify({
        'player': player,
        'best_score': player_best_score,
        'rank': player_rank,
        'total_players': total_players,
        'nearby': nearby_result
    }), 200


# 4. Get all scores for a player
@scores_blueprint.route('/scores/player/<player_id>', methods=['GET'])
def get_player_scores(player_id):
    """
    Get all scores for a player across all leaderboards
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
            description: List of all player's scores
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

    # Verify player exists
    players_collection = db['players']
    player = players_collection.find_one({
        '_id': player_id,
        'app_id': app['_id']
    })
    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    # Get all scores for this player
    scores_collection = db['scores']
    leaderboards_collection = db['leaderboards']

    # Get all leaderboards for this app
    app_leaderboards = {lb['_id']: lb for lb in leaderboards_collection.find({'app_id': app['_id']})}

    # Get player's scores only for this app's leaderboards
    player_scores = list(scores_collection.find({
        'player_id': player_id,
        'leaderboard_id': {'$in': list(app_leaderboards.keys())}
    }).sort('created_at', -1))

    # Enrich with leaderboard info
    result = []
    for score in player_scores:
        leaderboard = app_leaderboards.get(score['leaderboard_id'])
        result.append({
            'score': score,
            'leaderboard': leaderboard
        })

    return jsonify({
        'player': player,
        'scores': result
    }), 200
