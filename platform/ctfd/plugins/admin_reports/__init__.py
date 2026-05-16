import os

from flask import Blueprint, render_template
from CTFd.utils.decorators import admins_only


def load(app):
    bp = Blueprint(
        "admin_reports",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )

    @bp.route("/admin-reports")
    @admins_only
    def admin_reports():
        return render_template(
            "admin_reports.html",
            orch_base=os.getenv("ORCH_PUBLIC_BASE", "").rstrip("/"),
        )

    @bp.route("/admin-feedback")
    @admins_only
    def admin_feedback():
        return render_template(
            "admin_feedback.html",
            orch_base=os.getenv("ORCH_PUBLIC_BASE", "").rstrip("/"),
        )

    @bp.route("/admin-round-comparison")
    @admins_only
    def admin_round_comparison():
        return render_template(
            "admin_round_comparison.html",
            orch_base=os.getenv("ORCH_PUBLIC_BASE", "").rstrip("/"),
        )

    app.register_blueprint(bp)
