from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from controllers.apps_controller import validate_api_key
from datetime import datetime
import uuid

trophies_blueprint = Blueprint('trophies', __name__)


# ==================== TROPHY MANAGEMENT (Hub SDK) ====================

# 1. Create a new trophy
@trophies_blueprint.route('/trophies', methods=['POST'])
def create_trophy():
    """
    Create a new trophy/achievement definition
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
          description: The API key for authentication
        - name: trophy
          in: body
          required: true
          schema:
            properties:
                name:
                    type: string
                    description: Trophy name
                description:
                    type: string
                    description: Trophy description
                icon_url:
                    type: string
                    description: Trophy icon URL
                trophy_type:
                    type: string
                    enum: [point_based, count_based, manual]
                    description: Type of trophy trigger
                trigger:
                    type: object
                    description: Trigger configuration
                rarity:
                    type: string
                    enum: [common, rare, epic, legendary]
                points:
                    type: integer
                    description: Points awarded for earning trophy
    responses:
        201:
            description: Trophy created successfully
        400:
            description: Invalid input
        401:
            description: Invalid API key
    """
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
        return jsonify({'error': 'Trophy name is required'}), 400

    if 'trophy_type' not in data:
        return jsonify({'error': 'Trophy type is required'}), 400

    trophy_type = data['trophy_type']
    if trophy_type not in ['point_based', 'count_based', 'manual']:
        return jsonify({'error': 'Invalid trophy_type. Must be: point_based, count_based, or manual'}), 400

    # Validate trigger based on type
    trigger = data.get('trigger', {})
    if trophy_type == 'point_based':
        if 'threshold' not in trigger:
            return jsonify({'error': 'point_based trophy requires trigger.threshold'}), 400
        if not isinstance(trigger['threshold'], (int, float)) or trigger['threshold'] <= 0:
            return jsonify({'error': 'threshold must be a positive number'}), 400
    elif trophy_type == 'count_based':
        if 'count_target' not in trigger:
            return jsonify({'error': 'count_based trophy requires trigger.count_target'}), 400
        if not isinstance(trigger['count_target'], int) or trigger['count_target'] <= 0:
            return jsonify({'error': 'count_target must be a positive integer'}), 400
    elif trophy_type == 'manual':
        if 'event_key' not in trigger:
            return jsonify({'error': 'manual trophy requires trigger.event_key'}), 400

    rarity = data.get('rarity', 'common')
    if rarity not in ['common', 'rare', 'epic', 'legendary']:
        return jsonify({'error': 'Invalid rarity. Must be: common, rare, epic, or legendary'}), 400

    trophies_collection = db['trophies']

    # Check for duplicate name within same app
    existing = trophies_collection.find_one({
        'app_id': app['_id'],
        'name': data['name']
    })
    if existing:
        return jsonify({'error': 'A trophy with this name already exists'}), 409

    trophy_item = {
        "_id": str(uuid.uuid4()),
        "app_id": app['_id'],
        "name": data['name'],
        "description": data.get('description', ''),
        "icon_url": data.get('icon_url'),
        "trophy_type": trophy_type,
        "trigger": trigger,
        "rarity": rarity,
        "points": data.get('points', 10),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    trophies_collection.insert_one(trophy_item)

    return jsonify({
        'message': 'Trophy created successfully',
        'trophy': trophy_item
    }), 201


# 2. Get all trophies for an app
@trophies_blueprint.route('/trophies', methods=['GET'])
def get_trophies():
    """
    Get all trophies for the authenticated app
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
    responses:
        200:
            description: List of trophies
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    trophies_collection = db['trophies']
    trophies = list(trophies_collection.find({'app_id': app['_id']}))

    return jsonify({
        'trophies': trophies,
        'total': len(trophies)
    }), 200


# 3. Get trophy by ID
@trophies_blueprint.route('/trophies/<trophy_id>', methods=['GET'])
def get_trophy(trophy_id):
    """
    Get trophy by ID
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: trophy_id
          in: path
          type: string
          required: true
    responses:
        200:
            description: Trophy information
        404:
            description: Trophy not found
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    trophies_collection = db['trophies']
    trophy = trophies_collection.find_one({
        '_id': trophy_id,
        'app_id': app['_id']
    })

    if trophy is None:
        return jsonify({'error': 'Trophy not found'}), 404

    return jsonify({'trophy': trophy}), 200


# 4. Update trophy
@trophies_blueprint.route('/trophies/<trophy_id>', methods=['PUT'])
def update_trophy(trophy_id):
    """
    Update trophy configuration
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: trophy_id
          in: path
          type: string
          required: true
    responses:
        200:
            description: Trophy updated successfully
        404:
            description: Trophy not found
    """
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

    trophies_collection = db['trophies']
    trophy = trophies_collection.find_one({
        '_id': trophy_id,
        'app_id': app['_id']
    })

    if trophy is None:
        return jsonify({'error': 'Trophy not found'}), 404

    # Prevent modifying critical fields that would break existing progress
    if 'trophy_type' in data or 'trigger' in data:
        return jsonify({'error': 'Cannot modify trophy_type or trigger after creation'}), 400

    update_fields = {'updated_at': datetime.now().isoformat()}
    if 'name' in data:
        update_fields['name'] = data['name']
    if 'description' in data:
        update_fields['description'] = data['description']
    if 'icon_url' in data:
        update_fields['icon_url'] = data['icon_url']
    if 'points' in data:
        update_fields['points'] = data['points']
    if 'rarity' in data:
        if data['rarity'] in ['common', 'rare', 'epic', 'legendary']:
            update_fields['rarity'] = data['rarity']

    trophies_collection.update_one(
        {'_id': trophy_id},
        {'$set': update_fields}
    )

    updated_trophy = trophies_collection.find_one({'_id': trophy_id})

    return jsonify({
        'message': 'Trophy updated successfully',
        'trophy': updated_trophy
    }), 200


# 5. Delete trophy
@trophies_blueprint.route('/trophies/<trophy_id>', methods=['DELETE'])
def delete_trophy(trophy_id):
    """
    Delete a trophy and all player progress
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: trophy_id
          in: path
          type: string
          required: true
    responses:
        200:
            description: Trophy deleted successfully
        404:
            description: Trophy not found
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    trophies_collection = db['trophies']
    trophy = trophies_collection.find_one({
        '_id': trophy_id,
        'app_id': app['_id']
    })

    if trophy is None:
        return jsonify({'error': 'Trophy not found'}), 404

    # Delete all player trophies for this trophy
    player_trophies_collection = db['player_trophies']
    player_trophies_collection.delete_many({'trophy_id': trophy_id})

    # Delete the trophy
    trophies_collection.delete_one({'_id': trophy_id})

    return jsonify({'message': 'Trophy and all player progress deleted successfully'}), 200


# ==================== PLAYER TROPHIES (Game SDK) ====================

# 6. Get player's trophies with progress
@trophies_blueprint.route('/trophies/player/<player_id>', methods=['GET'])
def get_player_trophies(player_id):
    """
    Get all trophies and progress for a player
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: player_id
          in: path
          type: string
          required: true
        - name: status
          in: query
          type: string
          enum: [earned, in_progress]
          description: Filter by status
    responses:
        200:
            description: Player trophies with progress
        404:
            description: Player not found
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    # Verify player belongs to this app
    players_collection = db['players']
    player = players_collection.find_one({
        '_id': player_id,
        'app_id': app['_id']
    })

    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    status_filter = request.args.get('status')

    # Get all trophies for this app
    trophies_collection = db['trophies']
    all_trophies = list(trophies_collection.find({'app_id': app['_id']}))

    # Get player's trophy progress
    player_trophies_collection = db['player_trophies']
    query = {'player_id': player_id, 'app_id': app['_id']}
    if status_filter:
        query['status'] = status_filter

    player_trophy_records = {
        pt['trophy_id']: pt
        for pt in player_trophies_collection.find(query)
    }

    # Build response with trophy + progress
    trophies_with_progress = []
    total_earned = 0
    total_points = 0

    for trophy in all_trophies:
        player_trophy = player_trophy_records.get(trophy['_id'])

        if status_filter and not player_trophy:
            continue
        if status_filter and player_trophy.get('status') != status_filter:
            continue

        trophy_data = {
            'trophy': trophy,
            'player_trophy': player_trophy,
            'progress_percentage': 0.0
        }

        if player_trophy:
            if player_trophy['status'] == 'earned':
                trophy_data['progress_percentage'] = 100.0
                total_earned += 1
                total_points += trophy.get('points', 0)
            else:
                target = player_trophy.get('target_progress', 1)
                current = player_trophy.get('current_progress', 0)
                trophy_data['progress_percentage'] = (current / target * 100) if target > 0 else 0

        trophies_with_progress.append(trophy_data)

    return jsonify({
        'player': player,
        'trophies': trophies_with_progress,
        'stats': {
            'total_earned': total_earned,
            'total_available': len(all_trophies),
            'completion_percentage': (total_earned / len(all_trophies) * 100) if all_trophies else 0,
            'total_points': total_points
        }
    }), 200


# 7. Manually trigger trophy event
@trophies_blueprint.route('/trophies/trigger', methods=['POST'])
def trigger_trophy_event():
    """
    Manually trigger a trophy event for custom achievements
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: body
          in: body
          required: true
          schema:
            properties:
                player_id:
                    type: string
                event_key:
                    type: string
                custom_data:
                    type: object
    responses:
        200:
            description: Trophy event processed
    """
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

    if not data or 'player_id' not in data or 'event_key' not in data:
        return jsonify({'error': 'player_id and event_key are required'}), 400

    player_id = data['player_id']
    event_key = data['event_key']
    custom_data = data.get('custom_data', {})

    # Verify player
    players_collection = db['players']
    player = players_collection.find_one({
        '_id': player_id,
        'app_id': app['_id']
    })
    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    # Find matching manual trophies
    trophies_collection = db['trophies']
    matching_trophies = list(trophies_collection.find({
        'app_id': app['_id'],
        'trophy_type': 'manual',
        'trigger.event_key': event_key
    }))

    player_trophies_collection = db['player_trophies']
    newly_earned = []

    for trophy in matching_trophies:
        # Check if already earned
        existing = player_trophies_collection.find_one({
            'player_id': player_id,
            'trophy_id': trophy['_id']
        })

        if existing and existing.get('status') == 'earned':
            continue  # Already earned, skip

        # Award the trophy
        now = datetime.now().isoformat()

        if existing:
            # Update existing record
            player_trophies_collection.update_one(
                {'_id': existing['_id']},
                {'$set': {
                    'status': 'earned',
                    'earned_at': now,
                    'trigger_data': custom_data,
                    'updated_at': now
                }}
            )
        else:
            # Create new record
            player_trophy = {
                '_id': str(uuid.uuid4()),
                'player_id': player_id,
                'trophy_id': trophy['_id'],
                'app_id': app['_id'],
                'status': 'earned',
                'current_progress': 1,
                'target_progress': 1,
                'earned_at': now,
                'trigger_data': custom_data,
                'created_at': now,
                'updated_at': now
            }
            player_trophies_collection.insert_one(player_trophy)

        newly_earned.append(trophy)

    return jsonify({
        'message': f'Processed event: {event_key}',
        'newly_earned': newly_earned,
        'updated_progress': []
    }), 200


# 8. Get trophy progress for specific trophy/player
@trophies_blueprint.route('/trophies/<trophy_id>/player/<player_id>/progress', methods=['GET'])
def get_trophy_progress(trophy_id, player_id):
    """
    Get progress for a specific trophy
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: trophy_id
          in: path
          type: string
          required: true
        - name: player_id
          in: path
          type: string
          required: true
    responses:
        200:
            description: Trophy progress information
        404:
            description: Trophy or player not found
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    # Verify player belongs to this app
    players_collection = db['players']
    player = players_collection.find_one({
        '_id': player_id,
        'app_id': app['_id']
    })
    if player is None:
        return jsonify({'error': 'Player not found'}), 404

    # Get trophy
    trophies_collection = db['trophies']
    trophy = trophies_collection.find_one({
        '_id': trophy_id,
        'app_id': app['_id']
    })
    if trophy is None:
        return jsonify({'error': 'Trophy not found'}), 404

    # Get player trophy progress
    player_trophies_collection = db['player_trophies']
    player_trophy = player_trophies_collection.find_one({
        'player_id': player_id,
        'trophy_id': trophy_id
    })

    if player_trophy:
        current = player_trophy.get('current_progress', 0)
        target = player_trophy.get('target_progress', 1)
        percentage = (current / target * 100) if target > 0 else 0

        progress = {
            'status': player_trophy.get('status', 'in_progress'),
            'current': current,
            'target': target,
            'percentage': percentage,
            'remaining': max(0, target - current)
        }
    else:
        # No progress yet
        target = 1
        if trophy['trophy_type'] == 'point_based':
            target = trophy['trigger'].get('threshold', 1)
        elif trophy['trophy_type'] == 'count_based':
            target = trophy['trigger'].get('count_target', 1)

        progress = {
            'status': 'not_started',
            'current': 0,
            'target': target,
            'percentage': 0,
            'remaining': target
        }

    return jsonify({
        'trophy': trophy,
        'progress': progress
    }), 200


# ==================== TROPHY EVALUATOR ====================

def evaluate_trophies_on_score(db, app_id, player_id, score_value, leaderboard_id):
    """
    Evaluate and award trophies after a score submission.
    Called from scores_controller.
    Returns list of newly earned trophies.
    """
    trophies_collection = db['trophies']
    player_trophies_collection = db['player_trophies']
    scores_collection = db['scores']

    newly_earned = []

    # Get all non-manual trophies for this app
    trophies = list(trophies_collection.find({
        'app_id': app_id,
        'trophy_type': {'$in': ['point_based', 'count_based']}
    }))

    for trophy in trophies:
        trophy_id = trophy['_id']
        trophy_type = trophy['trophy_type']
        trigger = trophy.get('trigger', {})

        # Check if already earned
        existing = player_trophies_collection.find_one({
            'player_id': player_id,
            'trophy_id': trophy_id,
            'status': 'earned'
        })
        if existing:
            continue

        earned = False
        current_progress = 0
        target_progress = 1

        if trophy_type == 'point_based':
            threshold = trigger.get('threshold', 0)
            target_progress = threshold
            trophy_leaderboard = trigger.get('leaderboard_id')

            # Check if this is for a specific leaderboard
            if trophy_leaderboard and trophy_leaderboard != leaderboard_id:
                continue  # Not for this leaderboard

            # Check if score meets threshold
            if score_value >= threshold:
                earned = True
                current_progress = score_value

        elif trophy_type == 'count_based':
            count_target = trigger.get('count_target', 1)
            target_progress = count_target

            # Count total scores for this player in this app
            # Get all leaderboards for this app
            leaderboards = list(db['leaderboards'].find({'app_id': app_id}))
            lb_ids = [lb['_id'] for lb in leaderboards]

            score_count = scores_collection.count_documents({
                'player_id': player_id,
                'leaderboard_id': {'$in': lb_ids}
            })
            current_progress = score_count

            if score_count >= count_target:
                earned = True

        # Update or create player trophy record
        now = datetime.now().isoformat()
        existing_progress = player_trophies_collection.find_one({
            'player_id': player_id,
            'trophy_id': trophy_id
        })

        if earned:
            if existing_progress:
                player_trophies_collection.update_one(
                    {'_id': existing_progress['_id']},
                    {'$set': {
                        'status': 'earned',
                        'current_progress': current_progress,
                        'earned_at': now,
                        'trigger_data': {'score': score_value, 'leaderboard_id': leaderboard_id},
                        'updated_at': now
                    }}
                )
            else:
                player_trophies_collection.insert_one({
                    '_id': str(uuid.uuid4()),
                    'player_id': player_id,
                    'trophy_id': trophy_id,
                    'app_id': app_id,
                    'status': 'earned',
                    'current_progress': current_progress,
                    'target_progress': target_progress,
                    'earned_at': now,
                    'trigger_data': {'score': score_value, 'leaderboard_id': leaderboard_id},
                    'created_at': now,
                    'updated_at': now
                })
            newly_earned.append(trophy)
        else:
            # Update progress
            if existing_progress:
                player_trophies_collection.update_one(
                    {'_id': existing_progress['_id']},
                    {'$set': {
                        'current_progress': current_progress,
                        'updated_at': now
                    }}
                )
            else:
                player_trophies_collection.insert_one({
                    '_id': str(uuid.uuid4()),
                    'player_id': player_id,
                    'trophy_id': trophy_id,
                    'app_id': app_id,
                    'status': 'in_progress',
                    'current_progress': current_progress,
                    'target_progress': target_progress,
                    'earned_at': None,
                    'trigger_data': None,
                    'created_at': now,
                    'updated_at': now
                })

    return newly_earned
