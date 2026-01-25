from flask import request, jsonify, Blueprint
from mongodb_connection_holder import MongoConnectionHolder
from controllers.apps_controller import validate_api_key
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Safety limits to prevent memory exhaustion
MAX_LEADERBOARDS_PER_QUERY = 1000

stats_blueprint = Blueprint('stats', __name__)


def get_date_range(days):
    """Get start date for the given number of days ago."""
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")
    return (datetime.now() - timedelta(days=days)).isoformat()


def validate_leaderboard_id(leaderboard_id):
    """Validate leaderboard_id format."""
    if not leaderboard_id or not isinstance(leaderboard_id, str):
        return False
    if len(leaderboard_id) > 100:  # Reasonable max length
        return False
    return True


# 1. Get app overview statistics
@stats_blueprint.route('/stats/overview', methods=['GET'])
def get_app_overview_stats():
    """
    Get comprehensive overview statistics for the app
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
    responses:
        200:
            description: App overview statistics
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

    app_id = app['_id']

    # Get collections
    players_collection = db['players']
    leaderboards_collection = db['leaderboards']
    scores_collection = db['scores']

    # Initialize defaults
    total_players = 0
    total_leaderboards = 0
    leaderboard_ids = []
    total_scores = 0
    active_7d = 0
    active_30d = 0

    try:
        # Total players
        total_players = players_collection.count_documents({'app_id': app_id})

        # Total leaderboards
        total_leaderboards = leaderboards_collection.count_documents({'app_id': app_id})

        # Get leaderboard IDs for this app (with safety limit)
        leaderboard_cursor = leaderboards_collection.find({'app_id': app_id}).limit(MAX_LEADERBOARDS_PER_QUERY)
        leaderboard_ids = [lb['_id'] for lb in leaderboard_cursor]
        if len(leaderboard_ids) >= MAX_LEADERBOARDS_PER_QUERY:
            logger.warning(f"Leaderboard limit reached for app_id={app_id}, results may be incomplete")

        # Total scores across all leaderboards
        if leaderboard_ids:
            total_scores = scores_collection.count_documents({
                'leaderboard_id': {'$in': leaderboard_ids}
            })
    except Exception as e:
        logger.error(f"Error fetching basic stats for app_id={app_id}: {e}", exc_info=True)

    # Active players (7 days and 30 days)
    seven_days_ago = get_date_range(7)
    thirty_days_ago = get_date_range(30)

    if leaderboard_ids:
        try:
            # Get unique players with scores in last 7 days using aggregation
            pipeline_7d = [
                {'$match': {
                    'leaderboard_id': {'$in': leaderboard_ids},
                    'created_at': {'$gte': seven_days_ago}
                }},
                {'$group': {'_id': None, 'unique_players': {'$addToSet': '$player_id'}}},
                {'$project': {'count': {'$size': '$unique_players'}}}
            ]
            result_7d = list(scores_collection.aggregate(pipeline_7d))
            active_7d = result_7d[0]['count'] if result_7d else 0

            # Get unique players with scores in last 30 days using aggregation
            pipeline_30d = [
                {'$match': {
                    'leaderboard_id': {'$in': leaderboard_ids},
                    'created_at': {'$gte': thirty_days_ago}
                }},
                {'$group': {'_id': None, 'unique_players': {'$addToSet': '$player_id'}}},
                {'$project': {'count': {'$size': '$unique_players'}}}
            ]
            result_30d = list(scores_collection.aggregate(pipeline_30d))
            active_30d = result_30d[0]['count'] if result_30d else 0
        except Exception as e:
            logger.error(f"Error fetching active players for app_id={app_id}: {e}", exc_info=True)

    # Average score (if there are scores)
    avg_score = 0
    if leaderboard_ids and total_scores > 0:
        try:
            pipeline = [
                {'$match': {'leaderboard_id': {'$in': leaderboard_ids}}},
                {'$group': {'_id': None, 'avg': {'$avg': '$score'}}}
            ]
            result = list(scores_collection.aggregate(pipeline))
            if result:
                avg_score = round(result[0].get('avg', 0) or 0, 2)
        except Exception as e:
            logger.error(f"Error in avg score aggregation for app_id={app_id}: {e}", exc_info=True)
            avg_score = 0

    # New players today
    new_players_today = 0
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        new_players_today = players_collection.count_documents({
            'app_id': app_id,
            'created_at': {'$gte': today_start}
        })
    except Exception as e:
        logger.error(f"Error counting new players for app_id={app_id}: {e}", exc_info=True)

    return jsonify({
        'app_id': app_id,
        'app_name': app.get('name', ''),
        'stats': {
            'total_players': total_players,
            'active_players_7d': active_7d,
            'active_players_30d': active_30d,
            'total_scores': total_scores,
            'total_leaderboards': total_leaderboards,
            'average_score': avg_score,
            'new_players_today': new_players_today
        },
        'generated_at': datetime.now().isoformat()
    }), 200


# 2. Get daily score counts
@stats_blueprint.route('/stats/scores/daily', methods=['GET'])
def get_daily_scores():
    """
    Get daily score submission counts
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: days
          in: query
          type: integer
          default: 30
          description: Number of days to retrieve (max 90)
    responses:
        200:
            description: Daily score counts
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    days = request.args.get('days', 30, type=int)
    if days < 1 or days > 90:
        return jsonify({'error': 'days must be between 1 and 90'}), 400

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    app_id = app['_id']
    start_date = get_date_range(days)

    # Get leaderboard IDs for this app (with safety limit)
    leaderboards_collection = db['leaderboards']
    try:
        leaderboard_cursor = leaderboards_collection.find({'app_id': app_id}).limit(MAX_LEADERBOARDS_PER_QUERY)
        leaderboard_ids = [lb['_id'] for lb in leaderboard_cursor]
        if len(leaderboard_ids) >= MAX_LEADERBOARDS_PER_QUERY:
            logger.warning(f"Leaderboard limit reached for app_id={app_id}, results may be incomplete")
    except Exception as e:
        logger.error(f"Error fetching leaderboard IDs for app_id={app_id}: {e}", exc_info=True)
        leaderboard_ids = []

    if not leaderboard_ids:
        return jsonify({
            'app_id': app_id,
            'period_days': days,
            'data': [],
            'total_scores': 0,
            'generated_at': datetime.now().isoformat()
        }), 200

    scores_collection = db['scores']

    # Aggregate scores by day
    try:
        pipeline = [
            {
                '$match': {
                    'leaderboard_id': {'$in': leaderboard_ids},
                    'created_at': {'$gte': start_date}
                }
            },
            {
                '$project': {
                    'date': {'$substr': ['$created_at', 0, 10]}  # Extract YYYY-MM-DD
                }
            },
            {
                '$group': {
                    '_id': '$date',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'_id': 1}}
        ]

        result = list(scores_collection.aggregate(pipeline))
    except Exception as e:
        logger.error(f"Error in daily scores aggregation for app_id={app_id}: {e}", exc_info=True)
        result = []

    # Format result
    daily_data = [{'date': r['_id'], 'count': r['count']} for r in result]
    total_scores = sum(r['count'] for r in result)

    return jsonify({
        'app_id': app_id,
        'period_days': days,
        'data': daily_data,
        'total_scores': total_scores,
        'generated_at': datetime.now().isoformat()
    }), 200


# 3. Get leaderboard score distribution
@stats_blueprint.route('/stats/leaderboards/<leaderboard_id>/distribution', methods=['GET'])
def get_leaderboard_distribution(leaderboard_id):
    """
    Get score distribution for a leaderboard
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: leaderboard_id
          in: path
          type: string
          required: true
    responses:
        200:
            description: Score distribution
        404:
            description: Leaderboard not found
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    # Validate leaderboard_id format
    if not validate_leaderboard_id(leaderboard_id):
        return jsonify({'error': 'Invalid leaderboard ID format'}), 400

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    # Verify leaderboard belongs to this app
    leaderboards_collection = db['leaderboards']
    try:
        leaderboard = leaderboards_collection.find_one({
            '_id': leaderboard_id,
            'app_id': app['_id']
        })
    except Exception as e:
        logger.error(f"Error finding leaderboard_id={leaderboard_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error'}), 500

    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    scores_collection = db['scores']

    # Get basic stats
    try:
        pipeline_stats = [
            {'$match': {'leaderboard_id': leaderboard_id}},
            {
                '$group': {
                    '_id': None,
                    'count': {'$sum': 1},
                    'min': {'$min': '$score'},
                    'max': {'$max': '$score'},
                    'avg': {'$avg': '$score'}
                }
            }
        ]

        stats_result = list(scores_collection.aggregate(pipeline_stats))
    except Exception as e:
        logger.error(f"Error in distribution stats for leaderboard_id={leaderboard_id}: {e}", exc_info=True)
        stats_result = []

    if not stats_result:
        return jsonify({
            'leaderboard_id': leaderboard_id,
            'leaderboard_name': leaderboard.get('name', ''),
            'distribution': [],
            'total_scores': 0,
            'min_score': 0,
            'max_score': 0,
            'avg_score': 0,
            'generated_at': datetime.now().isoformat()
        }), 200

    stats = stats_result[0]
    total_scores = stats['count']
    min_score = stats['min']
    max_score = stats['max']
    avg_score = round(stats['avg'], 2)

    # Create score buckets
    # Define bucket boundaries
    boundaries = [0, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]

    # Filter boundaries to be within actual score range
    relevant_boundaries = [b for b in boundaries if b <= max_score]
    if not relevant_boundaries or relevant_boundaries[-1] < max_score:
        relevant_boundaries.append(max_score + 1)

    # Aggregate into buckets
    pipeline_dist = [
        {'$match': {'leaderboard_id': leaderboard_id}},
        {
            '$bucket': {
                'groupBy': '$score',
                'boundaries': relevant_boundaries if len(relevant_boundaries) >= 2 else [0, max_score + 1],
                'default': 'Other',
                'output': {'count': {'$sum': 1}}
            }
        }
    ]

    try:
        dist_result = list(scores_collection.aggregate(pipeline_dist))
    except Exception as e:
        logger.error(f"Error in bucket aggregation for leaderboard_id={leaderboard_id}: {e}", exc_info=True)
        dist_result = []

    # Format distribution
    distribution = []
    for bucket in dist_result:
        bucket_id = bucket['_id']
        count = bucket['count']
        percentage = round((count / total_scores) * 100, 1) if total_scores > 0 else 0

        if bucket_id == 'Other':
            range_str = f'{relevant_boundaries[-1]}+'
        else:
            # Find the next boundary
            idx = relevant_boundaries.index(bucket_id) if bucket_id in relevant_boundaries else 0
            next_boundary = relevant_boundaries[idx + 1] - 1 if idx + 1 < len(relevant_boundaries) else bucket_id
            range_str = f'{bucket_id}-{next_boundary}'

        distribution.append({
            'range': range_str,
            'count': count,
            'percentage': percentage
        })

    return jsonify({
        'leaderboard_id': leaderboard_id,
        'leaderboard_name': leaderboard.get('name', ''),
        'distribution': distribution,
        'total_scores': total_scores,
        'min_score': min_score,
        'max_score': max_score,
        'avg_score': avg_score,
        'generated_at': datetime.now().isoformat()
    }), 200


# 4. Get player activity timeline
@stats_blueprint.route('/stats/players/activity', methods=['GET'])
def get_player_activity_timeline():
    """
    Get player activity timeline (new and active players per day)
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: days
          in: query
          type: integer
          default: 30
          description: Number of days to retrieve (max 90)
    responses:
        200:
            description: Player activity timeline
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    days = request.args.get('days', 30, type=int)
    if days < 1 or days > 90:
        return jsonify({'error': 'days must be between 1 and 90'}), 400

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    app_id = app['_id']
    start_date = get_date_range(days)

    players_collection = db['players']
    scores_collection = db['scores']
    leaderboards_collection = db['leaderboards']

    # Get leaderboard IDs (with safety limit)
    try:
        leaderboard_cursor = leaderboards_collection.find({'app_id': app_id}).limit(MAX_LEADERBOARDS_PER_QUERY)
        leaderboard_ids = [lb['_id'] for lb in leaderboard_cursor]
        if len(leaderboard_ids) >= MAX_LEADERBOARDS_PER_QUERY:
            logger.warning(f"Leaderboard limit reached for app_id={app_id}, results may be incomplete")
    except Exception as e:
        logger.error(f"Error fetching leaderboard IDs for app_id={app_id}: {e}", exc_info=True)
        leaderboard_ids = []

    # New players per day
    try:
        new_players_pipeline = [
            {
                '$match': {
                    'app_id': app_id,
                    'created_at': {'$gte': start_date}
                }
            },
            {
                '$project': {
                    'date': {'$substr': ['$created_at', 0, 10]}
                }
            },
            {
                '$group': {
                    '_id': '$date',
                    'new_players': {'$sum': 1}
                }
            },
            {'$sort': {'_id': 1}}
        ]

        new_players_result = list(players_collection.aggregate(new_players_pipeline))
        new_players_by_date = {r['_id']: r['new_players'] for r in new_players_result}
    except Exception as e:
        logger.error(f"Error in new players aggregation for app_id={app_id}: {e}", exc_info=True)
        new_players_by_date = {}

    # Active players per day (from scores)
    active_players_by_date = {}
    if leaderboard_ids:
        try:
            active_players_pipeline = [
                {
                    '$match': {
                        'leaderboard_id': {'$in': leaderboard_ids},
                        'created_at': {'$gte': start_date}
                    }
                },
                {
                    '$project': {
                        'date': {'$substr': ['$created_at', 0, 10]},
                        'player_id': 1
                    }
                },
                {
                    '$group': {
                        '_id': {'date': '$date', 'player_id': '$player_id'}
                    }
                },
                {
                    '$group': {
                        '_id': '$_id.date',
                        'active_players': {'$sum': 1}
                    }
                },
                {'$sort': {'_id': 1}}
            ]

            active_result = list(scores_collection.aggregate(active_players_pipeline))
            active_players_by_date = {r['_id']: r['active_players'] for r in active_result}
        except Exception as e:
            logger.error(f"Error in active players aggregation for app_id={app_id}: {e}", exc_info=True)
            active_players_by_date = {}

    # Merge data into timeline
    all_dates = sorted(set(list(new_players_by_date.keys()) + list(active_players_by_date.keys())))

    timeline = []
    total_new = 0
    total_active_days = 0

    for date in all_dates:
        new_p = new_players_by_date.get(date, 0)
        active_p = active_players_by_date.get(date, 0)
        total_new += new_p
        if active_p > 0:
            total_active_days += active_p

        timeline.append({
            'date': date,
            'new_players': new_p,
            'active_players': active_p
        })

    avg_daily_active = round(total_active_days / len(timeline), 1) if timeline else 0

    return jsonify({
        'app_id': app_id,
        'period_days': days,
        'timeline': timeline,
        'summary': {
            'total_new_players': total_new,
            'avg_daily_active': avg_daily_active
        },
        'generated_at': datetime.now().isoformat()
    }), 200


# 5. Get leaderboard stats summary
@stats_blueprint.route('/stats/leaderboards/<leaderboard_id>', methods=['GET'])
def get_leaderboard_stats(leaderboard_id):
    """
    Get statistics for a specific leaderboard
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
        - name: leaderboard_id
          in: path
          type: string
          required: true
        - name: days
          in: query
          type: integer
          default: 30
    responses:
        200:
            description: Leaderboard statistics
        404:
            description: Leaderboard not found
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 401

    app = validate_api_key(api_key)
    if app is None:
        return jsonify({'error': 'Invalid API key'}), 401

    days = request.args.get('days', 30, type=int)
    if days < 1 or days > 90:
        return jsonify({'error': 'days must be between 1 and 90'}), 400

    # Validate leaderboard_id format
    if not validate_leaderboard_id(leaderboard_id):
        return jsonify({'error': 'Invalid leaderboard ID format'}), 400

    db = MongoConnectionHolder.get_db()
    if db is None:
        return jsonify({'error': 'Could not connect to the database'}), 500

    # Verify leaderboard
    leaderboards_collection = db['leaderboards']
    try:
        leaderboard = leaderboards_collection.find_one({
            '_id': leaderboard_id,
            'app_id': app['_id']
        })
    except Exception as e:
        logger.error(f"Error finding leaderboard_id={leaderboard_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error'}), 500

    if leaderboard is None:
        return jsonify({'error': 'Leaderboard not found'}), 404

    scores_collection = db['scores']
    start_date = get_date_range(days)

    # Get score stats
    try:
        pipeline = [
            {'$match': {'leaderboard_id': leaderboard_id}},
            {
                '$group': {
                    '_id': None,
                    'total_scores': {'$sum': 1},
                    'unique_players': {'$addToSet': '$player_id'},
                    'avg_score': {'$avg': '$score'},
                    'max_score': {'$max': '$score'},
                    'min_score': {'$min': '$score'}
                }
            }
        ]

        result = list(scores_collection.aggregate(pipeline))
    except Exception as e:
        logger.error(f"Error in leaderboard stats for leaderboard_id={leaderboard_id}: {e}", exc_info=True)
        result = []

    if not result:
        return jsonify({
            'leaderboard_id': leaderboard_id,
            'leaderboard_name': leaderboard.get('name', ''),
            'stats': {
                'total_scores': 0,
                'unique_players': 0,
                'avg_score': 0,
                'max_score': 0,
                'min_score': 0
            },
            'recent_activity': {
                'scores_in_period': 0,
                'active_players': 0
            },
            'generated_at': datetime.now().isoformat()
        }), 200

    stats = result[0]

    # Get recent activity
    try:
        recent_pipeline = [
            {
                '$match': {
                    'leaderboard_id': leaderboard_id,
                    'created_at': {'$gte': start_date}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'scores_count': {'$sum': 1},
                    'players': {'$addToSet': '$player_id'}
                }
            }
        ]

        recent_result = list(scores_collection.aggregate(recent_pipeline))
    except Exception as e:
        logger.error(f"Error in recent activity for leaderboard_id={leaderboard_id}: {e}", exc_info=True)
        recent_result = []

    recent_scores = 0
    recent_players = 0
    if recent_result:
        recent_scores = recent_result[0].get('scores_count', 0)
        recent_players = len(recent_result[0].get('players', []))

    return jsonify({
        'leaderboard_id': leaderboard_id,
        'leaderboard_name': leaderboard.get('name', ''),
        'stats': {
            'total_scores': stats['total_scores'],
            'unique_players': len(stats['unique_players']),
            'avg_score': round(stats['avg_score'], 2) if stats['avg_score'] else 0,
            'max_score': stats['max_score'],
            'min_score': stats['min_score']
        },
        'recent_activity': {
            'period_days': days,
            'scores_in_period': recent_scores,
            'active_players': recent_players
        },
        'generated_at': datetime.now().isoformat()
    }), 200


# 6. Get trophy analytics
@stats_blueprint.route('/stats/trophies', methods=['GET'])
def get_trophy_stats():
    """
    Get detailed trophy/achievement analytics
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
    responses:
        200:
            description: Trophy analytics with earn rates and rarity distribution
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

    app_id = app['_id']

    trophies_collection = db['trophies']
    player_trophies_collection = db['player_trophies']
    players_collection = db['players']

    # Get total players for earn rate calculation
    total_players = players_collection.count_documents({'app_id': app_id})

    # Get all trophies for this app
    trophies = list(trophies_collection.find({'app_id': app_id}))

    if not trophies:
        return jsonify({
            'app_id': app_id,
            'total_trophies': 0,
            'total_awarded': 0,
            'overall_completion_rate': 0,
            'trophies': [],
            'rarity_distribution': {},
            'generated_at': datetime.now().isoformat()
        }), 200

    trophy_analytics = []
    total_awarded = 0
    rarity_counts = {'common': [], 'rare': [], 'epic': [], 'legendary': []}

    for trophy in trophies:
        trophy_id = trophy['_id']

        # Get earned count
        earned_records = list(player_trophies_collection.find({
            'trophy_id': trophy_id,
            'status': 'earned'
        }))
        times_earned = len(earned_records)
        total_awarded += times_earned

        # Calculate earn rate
        earn_rate = round((times_earned / total_players * 100), 1) if total_players > 0 else 0

        # Calculate average days to earn
        avg_days = None
        first_earned = None
        last_earned = None

        if earned_records:
            earned_dates = []
            for record in earned_records:
                if record.get('earned_at') and record.get('created_at'):
                    try:
                        earned_dt = datetime.fromisoformat(record['earned_at'].replace('Z', '+00:00'))
                        created_dt = datetime.fromisoformat(record['created_at'].replace('Z', '+00:00'))
                        days_diff = (earned_dt - created_dt).days
                        if days_diff >= 0:
                            earned_dates.append(days_diff)
                    except (ValueError, TypeError):
                        pass

            if earned_dates:
                avg_days = round(sum(earned_dates) / len(earned_dates), 1)

            # Get first and last earned dates
            earned_at_dates = [r.get('earned_at') for r in earned_records if r.get('earned_at')]
            if earned_at_dates:
                earned_at_dates.sort()
                first_earned = earned_at_dates[0][:10] if earned_at_dates[0] else None
                last_earned = earned_at_dates[-1][:10] if earned_at_dates[-1] else None

        trophy_data = {
            'trophy_id': trophy_id,
            'name': trophy.get('name', ''),
            'description': trophy.get('description', ''),
            'rarity': trophy.get('rarity', 'common'),
            'points': trophy.get('points', 0),
            'times_earned': times_earned,
            'earn_rate_percent': earn_rate,
            'avg_days_to_earn': avg_days,
            'first_earned': first_earned,
            'last_earned': last_earned
        }
        trophy_analytics.append(trophy_data)

        # Track for rarity distribution
        rarity = trophy.get('rarity', 'common')
        if rarity in rarity_counts:
            rarity_counts[rarity].append(earn_rate)

    # Calculate rarity distribution stats
    rarity_distribution = {}
    for rarity, rates in rarity_counts.items():
        if rates:
            rarity_distribution[rarity] = {
                'total': len(rates),
                'avg_earn_rate': round(sum(rates) / len(rates), 1)
            }
        else:
            rarity_distribution[rarity] = {'total': 0, 'avg_earn_rate': 0}

    # Overall completion rate (avg of all trophy earn rates)
    all_earn_rates = [t['earn_rate_percent'] for t in trophy_analytics]
    overall_completion = round(sum(all_earn_rates) / len(all_earn_rates), 1) if all_earn_rates else 0

    # Sort by earn rate descending
    trophy_analytics.sort(key=lambda x: x['times_earned'], reverse=True)

    return jsonify({
        'app_id': app_id,
        'total_trophies': len(trophies),
        'total_awarded': total_awarded,
        'overall_completion_rate': overall_completion,
        'trophies': trophy_analytics,
        'rarity_distribution': rarity_distribution,
        'generated_at': datetime.now().isoformat()
    }), 200


# 7. Get engagement metrics
@stats_blueprint.route('/stats/engagement', methods=['GET'])
def get_engagement_stats():
    """
    Get player engagement metrics including play counts and activity patterns
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
    responses:
        200:
            description: Engagement statistics
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

    app_id = app['_id']

    scores_collection = db['scores']
    players_collection = db['players']
    leaderboards_collection = db['leaderboards']

    # Get leaderboard IDs
    leaderboard_ids = [lb['_id'] for lb in leaderboards_collection.find({'app_id': app_id}).limit(MAX_LEADERBOARDS_PER_QUERY)]

    if not leaderboard_ids:
        return jsonify({
            'app_id': app_id,
            'total_plays': 0,
            'unique_players': 0,
            'avg_plays_per_player': 0,
            'play_frequency': {'daily_active': 0, 'weekly_active': 0, 'monthly_active': 0},
            'peak_activity': {'hour_of_day': 0, 'day_of_week': 'N/A'},
            'plays_distribution': [],
            'generated_at': datetime.now().isoformat()
        }), 200

    # Total plays (score submissions)
    total_plays = scores_collection.count_documents({'leaderboard_id': {'$in': leaderboard_ids}})

    # Unique players
    unique_players = players_collection.count_documents({'app_id': app_id})

    # Average plays per player
    avg_plays = round(total_plays / unique_players, 1) if unique_players > 0 else 0

    # Play frequency (DAU, WAU, MAU)
    now = datetime.now()
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    # Daily active (last 24h)
    daily_pipeline = [
        {'$match': {'leaderboard_id': {'$in': leaderboard_ids}, 'created_at': {'$gte': day_ago}}},
        {'$group': {'_id': '$player_id'}},
        {'$count': 'count'}
    ]
    daily_result = list(scores_collection.aggregate(daily_pipeline))
    daily_active = daily_result[0]['count'] if daily_result else 0

    # Weekly active
    weekly_pipeline = [
        {'$match': {'leaderboard_id': {'$in': leaderboard_ids}, 'created_at': {'$gte': week_ago}}},
        {'$group': {'_id': '$player_id'}},
        {'$count': 'count'}
    ]
    weekly_result = list(scores_collection.aggregate(weekly_pipeline))
    weekly_active = weekly_result[0]['count'] if weekly_result else 0

    # Monthly active
    monthly_pipeline = [
        {'$match': {'leaderboard_id': {'$in': leaderboard_ids}, 'created_at': {'$gte': month_ago}}},
        {'$group': {'_id': '$player_id'}},
        {'$count': 'count'}
    ]
    monthly_result = list(scores_collection.aggregate(monthly_pipeline))
    monthly_active = monthly_result[0]['count'] if monthly_result else 0

    # Peak activity (hour of day and day of week)
    # This requires parsing timestamps - use aggregation with date operators
    peak_hour_pipeline = [
        {'$match': {'leaderboard_id': {'$in': leaderboard_ids}}},
        {'$project': {
            'hour': {'$hour': {'$dateFromString': {'dateString': '$created_at', 'onError': None}}}
        }},
        {'$match': {'hour': {'$ne': None}}},
        {'$group': {'_id': '$hour', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 1}
    ]

    try:
        peak_hour_result = list(scores_collection.aggregate(peak_hour_pipeline))
        peak_hour = peak_hour_result[0]['_id'] if peak_hour_result else 12
    except Exception:
        peak_hour = 12

    # Day of week
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    peak_day_pipeline = [
        {'$match': {'leaderboard_id': {'$in': leaderboard_ids}}},
        {'$project': {
            'dayOfWeek': {'$dayOfWeek': {'$dateFromString': {'dateString': '$created_at', 'onError': None}}}
        }},
        {'$match': {'dayOfWeek': {'$ne': None}}},
        {'$group': {'_id': '$dayOfWeek', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 1}
    ]

    try:
        peak_day_result = list(scores_collection.aggregate(peak_day_pipeline))
        peak_day_num = peak_day_result[0]['_id'] if peak_day_result else 1
        peak_day = day_names[peak_day_num - 1] if 1 <= peak_day_num <= 7 else 'Saturday'
    except Exception:
        peak_day = 'Saturday'

    # Plays distribution (how many players have 1-5 plays, 6-20, etc.)
    plays_dist_pipeline = [
        {'$match': {'leaderboard_id': {'$in': leaderboard_ids}}},
        {'$group': {'_id': '$player_id', 'play_count': {'$sum': 1}}},
        {'$bucket': {
            'groupBy': '$play_count',
            'boundaries': [1, 6, 21, 51, 101],
            'default': '100+',
            'output': {'player_count': {'$sum': 1}}
        }}
    ]

    try:
        plays_dist_result = list(scores_collection.aggregate(plays_dist_pipeline))
    except Exception:
        plays_dist_result = []

    # Format distribution
    range_labels = {1: '1-5', 6: '6-20', 21: '21-50', 51: '51-100', '100+': '100+'}
    plays_distribution = []
    for bucket in plays_dist_result:
        bucket_id = bucket['_id']
        range_str = range_labels.get(bucket_id, str(bucket_id))
        plays_distribution.append({
            'plays_range': range_str,
            'player_count': bucket['player_count']
        })

    return jsonify({
        'app_id': app_id,
        'total_plays': total_plays,
        'unique_players': unique_players,
        'avg_plays_per_player': avg_plays,
        'play_frequency': {
            'daily_active': daily_active,
            'weekly_active': weekly_active,
            'monthly_active': monthly_active
        },
        'peak_activity': {
            'hour_of_day': peak_hour,
            'day_of_week': peak_day
        },
        'plays_distribution': plays_distribution,
        'generated_at': datetime.now().isoformat()
    }), 200


# 8. Get leaderboard competition stats
@stats_blueprint.route('/stats/competition', methods=['GET'])
def get_competition_stats():
    """
    Get competition statistics for all leaderboards
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
    responses:
        200:
            description: Competition statistics per leaderboard
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

    app_id = app['_id']

    leaderboards_collection = db['leaderboards']
    scores_collection = db['scores']

    leaderboards = list(leaderboards_collection.find({'app_id': app_id}).limit(50))

    if not leaderboards:
        return jsonify({
            'app_id': app_id,
            'leaderboards': [],
            'generated_at': datetime.now().isoformat()
        }), 200

    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    leaderboard_stats = []

    for lb in leaderboards:
        lb_id = lb['_id']

        # Get all scores for this leaderboard
        scores = list(scores_collection.find({'leaderboard_id': lb_id}))

        if not scores:
            leaderboard_stats.append({
                'leaderboard_id': lb_id,
                'name': lb.get('name', ''),
                'total_participants': 0,
                'avg_attempts_per_player': 0,
                'score_improvement_rate': 0,
                'top_score': 0,
                'median_score': 0,
                'competition_intensity': 'none',
                'recent_rank_changes': 0
            })
            continue

        # Group by player
        player_scores = {}
        for s in scores:
            pid = s['player_id']
            if pid not in player_scores:
                player_scores[pid] = []
            player_scores[pid].append(s)

        total_participants = len(player_scores)
        total_attempts = len(scores)
        avg_attempts = round(total_attempts / total_participants, 1) if total_participants > 0 else 0

        # Score improvement rate (% of players who improved their score)
        improved_count = 0
        for pid, pscores in player_scores.items():
            if len(pscores) >= 2:
                # Sort by created_at
                sorted_scores = sorted(pscores, key=lambda x: x.get('created_at', ''))
                first_score = sorted_scores[0]['score']
                best_score = max(s['score'] for s in sorted_scores)
                if best_score > first_score:
                    improved_count += 1

        improvement_rate = round((improved_count / total_participants * 100), 1) if total_participants > 0 else 0

        # Top and median score
        all_score_values = [s['score'] for s in scores]
        all_score_values.sort()
        top_score = max(all_score_values) if all_score_values else 0
        median_score = all_score_values[len(all_score_values) // 2] if all_score_values else 0

        # Competition intensity based on score variance
        if len(all_score_values) >= 2:
            score_range = top_score - min(all_score_values)
            avg_score = sum(all_score_values) / len(all_score_values)
            variance_ratio = score_range / avg_score if avg_score > 0 else 0

            if variance_ratio > 2:
                intensity = 'high'
            elif variance_ratio > 0.5:
                intensity = 'medium'
            else:
                intensity = 'low'
        else:
            intensity = 'low'

        # Recent rank changes (simplified: count new scores in last 7 days)
        recent_scores = [s for s in scores if s.get('created_at', '') >= week_ago]
        recent_rank_changes = len(recent_scores)

        leaderboard_stats.append({
            'leaderboard_id': lb_id,
            'name': lb.get('name', ''),
            'total_participants': total_participants,
            'avg_attempts_per_player': avg_attempts,
            'score_improvement_rate': improvement_rate,
            'top_score': top_score,
            'median_score': median_score,
            'competition_intensity': intensity,
            'recent_rank_changes': recent_rank_changes
        })

    return jsonify({
        'app_id': app_id,
        'leaderboards': leaderboard_stats,
        'generated_at': datetime.now().isoformat()
    }), 200


# 9. Get player segments
@stats_blueprint.route('/stats/segments', methods=['GET'])
def get_player_segments():
    """
    Get player segmentation analytics
    ---
    parameters:
        - name: X-API-Key
          in: header
          type: string
          required: true
    responses:
        200:
            description: Player segments with counts and metrics
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

    app_id = app['_id']

    players_collection = db['players']
    scores_collection = db['scores']
    player_trophies_collection = db['player_trophies']
    leaderboards_collection = db['leaderboards']

    # Get all players
    players = list(players_collection.find({'app_id': app_id}))

    if not players:
        return jsonify({
            'app_id': app_id,
            'segments': {},
            'generated_at': datetime.now().isoformat()
        }), 200

    # Get leaderboard IDs
    leaderboard_ids = [lb['_id'] for lb in leaderboards_collection.find({'app_id': app_id}).limit(MAX_LEADERBOARDS_PER_QUERY)]

    # Calculate plays per player
    player_plays = {}
    player_best_scores = {}

    if leaderboard_ids:
        plays_pipeline = [
            {'$match': {'leaderboard_id': {'$in': leaderboard_ids}}},
            {'$group': {
                '_id': '$player_id',
                'play_count': {'$sum': 1},
                'best_score': {'$max': '$score'}
            }}
        ]
        plays_result = list(scores_collection.aggregate(plays_pipeline))
        player_plays = {r['_id']: r['play_count'] for r in plays_result}
        player_best_scores = {r['_id']: r['best_score'] for r in plays_result}

    # Get trophies per player
    trophies_pipeline = [
        {'$match': {'app_id': app_id, 'status': 'earned'}},
        {'$group': {'_id': '$player_id', 'trophy_count': {'$sum': 1}}}
    ]
    trophies_result = list(player_trophies_collection.aggregate(trophies_pipeline))
    player_trophies = {r['_id']: r['trophy_count'] for r in trophies_result}

    # Time boundaries
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    # Segment players
    segments = {
        'top_players': {'players': [], 'criteria': 'top 10% by best score'},
        'casual': {'players': [], 'criteria': '1-5 plays total'},
        'regular': {'players': [], 'criteria': '6-20 plays total'},
        'hardcore': {'players': [], 'criteria': '21+ plays total'},
        'new_players': {'players': [], 'criteria': 'joined in last 7 days'},
        'veteran_players': {'players': [], 'criteria': 'joined 30+ days ago'}
    }

    # Find top 10% threshold
    all_best_scores = list(player_best_scores.values())
    if all_best_scores:
        all_best_scores.sort(reverse=True)
        top_10_threshold = all_best_scores[max(0, len(all_best_scores) // 10 - 1)]
    else:
        top_10_threshold = float('inf')

    for player in players:
        pid = player['_id']
        plays = player_plays.get(pid, 0)
        trophies = player_trophies.get(pid, 0)
        best_score = player_best_scores.get(pid, 0)
        created_at = player.get('created_at', '')

        player_data = {'plays': plays, 'trophies': trophies}

        # Segment by plays
        if plays <= 5:
            segments['casual']['players'].append(player_data)
        elif plays <= 20:
            segments['regular']['players'].append(player_data)
        else:
            segments['hardcore']['players'].append(player_data)

        # Top players
        if best_score >= top_10_threshold and best_score > 0:
            segments['top_players']['players'].append(player_data)

        # New vs veteran
        if created_at >= week_ago:
            segments['new_players']['players'].append(player_data)
        elif created_at < month_ago:
            segments['veteran_players']['players'].append(player_data)

    # Calculate segment stats
    result_segments = {}
    for segment_name, data in segments.items():
        players_list = data['players']
        count = len(players_list)

        if count > 0:
            avg_plays = round(sum(p['plays'] for p in players_list) / count, 1)
            avg_trophies = round(sum(p['trophies'] for p in players_list) / count, 1)
        else:
            avg_plays = 0
            avg_trophies = 0

        result_segments[segment_name] = {
            'count': count,
            'criteria': data['criteria'],
            'avg_plays': avg_plays,
            'avg_trophies': avg_trophies
        }

    return jsonify({
        'app_id': app_id,
        'segments': result_segments,
        'generated_at': datetime.now().isoformat()
    }), 200
