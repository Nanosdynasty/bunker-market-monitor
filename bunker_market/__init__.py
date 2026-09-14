import atexit
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from .config import Config
from .demo import seed_demo_data
from .models import db
from .refresh import ensure_provider_states, perform_refresh
from .graph_connector import refresh_all_cloud
from .routes import bp


scheduler = BackgroundScheduler(daemon=True, timezone="UTC")


def create_app(test_config=None):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        ensure_provider_states()
        if app.config["DEMO_MODE"]:
            seed_demo_data()

    if app.config["ENABLE_SCHEDULER"] and not app.config.get("TESTING"):
        job_id = "provider-refresh"
        if not scheduler.get_job(job_id):
            scheduler.add_job(
                lambda: _scheduled_refresh(app),
                "interval",
                minutes=app.config["REFRESH_INTERVAL_MINUTES"],
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                )
        graph_job_id = "cloud-workbook-refresh"
        if not scheduler.get_job(graph_job_id):
            scheduler.add_job(
                lambda: _scheduled_cloud_refresh(app),
                "interval",
                minutes=app.config["GRAPH_REFRESH_INTERVAL_MINUTES"],
                id=graph_job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        if not scheduler.running:
            scheduler.start()

    return app


def _scheduled_refresh(app):
    with app.app_context():
        perform_refresh(trigger="scheduled", force=False)


def _scheduled_cloud_refresh(app):
    with app.app_context():
        refresh_all_cloud()


@atexit.register
def _shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
