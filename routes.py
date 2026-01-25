from controllers.apps_controller import apps_blueprint
from controllers.players_controller import players_blueprint
from controllers.leaderboards_controller import leaderboards_blueprint
from controllers.scores_controller import scores_blueprint
from controllers.users_controller import users_blueprint
from controllers.trophies_controller import trophies_blueprint
from controllers.stats_controller import stats_blueprint


def init_routes(app):
    app.register_blueprint(apps_blueprint)
    app.register_blueprint(players_blueprint)
    app.register_blueprint(leaderboards_blueprint)
    app.register_blueprint(scores_blueprint)
    app.register_blueprint(users_blueprint)
    app.register_blueprint(trophies_blueprint)
    app.register_blueprint(stats_blueprint)
