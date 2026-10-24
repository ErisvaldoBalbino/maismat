import os

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # Uso pessoal/local: a chave só assina as mensagens de aviso (flash).
        SECRET_KEY=os.environ.get("MAISMAT_SECRET_KEY", "dev"),
        DATABASE=os.path.join(app.instance_path, "maismat.sqlite"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import db, routes

    db.init_app(app)
    app.register_blueprint(routes.bp)

    # Cria as tabelas automaticamente na primeira execução.
    with app.app_context():
        db.init_db()

    return app
