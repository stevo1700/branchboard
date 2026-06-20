"""
Branchboard — branching conversation board with contradiction flagging.
Flask + SQLAlchemy backend. Works on Postgres (Railway) or SQLite (local).
"""
import os
import uuid
import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__, static_folder="static", static_url_path="")

# --- database config: Postgres on Railway, SQLite locally ---
db_url = os.environ.get("DATABASE_URL", "sqlite:///branchboard.db")
if db_url.startswith("postgres://"):           # Railway gives postgres://, SQLAlchemy wants postgresql://
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


def new_id():
    return uuid.uuid4().hex[:12]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ------------------------------------------------------------------ #
# Models                                                             #
# ------------------------------------------------------------------ #
class Node(db.Model):
    id = db.Column(db.String(16), primary_key=True)
    text = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(120), nullable=False, default="Anonymous")
    parent_id = db.Column(db.String(16), nullable=True, index=True)
    depth = db.Column(db.Integer, nullable=False, default=0)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.String(40), nullable=False, default=now)


class Link(db.Model):
    id = db.Column(db.String(16), primary_key=True)
    a_id = db.Column(db.String(16), nullable=False)
    b_id = db.Column(db.String(16), nullable=False)
    reporter = db.Column(db.String(120), nullable=False, default="Anonymous")
    created_at = db.Column(db.String(40), nullable=False, default=now)
    status = db.Column(db.String(16), nullable=False, default="open")
    res_text = db.Column(db.Text, nullable=True)
    res_verdict = db.Column(db.String(16), nullable=True)
    resolver = db.Column(db.String(120), nullable=True)
    resolved_at = db.Column(db.String(40), nullable=True)


with app.app_context():
    db.create_all()


# ------------------------------------------------------------------ #
# Serialization                                                       #
# ------------------------------------------------------------------ #
def build_state():
    nodes = Node.query.order_by(Node.position.asc(), Node.created_at.asc()).all()
    out = {}
    root_order = []
    for n in nodes:
        out[n.id] = {
            "id": n.id, "text": n.text, "author": n.author,
            "parentId": n.parent_id, "children": [], "depth": n.depth,
            "createdAt": n.created_at,
        }
    for n in nodes:
        if n.parent_id and n.parent_id in out:
            out[n.parent_id]["children"].append(n.id)
        elif n.parent_id is None:
            root_order.append(n.id)

    links = []
    for l in Link.query.order_by(Link.created_at.asc()).all():
        links.append({
            "id": l.id, "a": l.a_id, "b": l.b_id, "reporter": l.reporter,
            "createdAt": l.created_at, "status": l.status,
            "resolution": None if l.status != "resolved" else {
                "text": l.res_text or "", "verdict": l.res_verdict,
                "resolver": l.resolver, "resolvedAt": l.resolved_at,
            },
        })
    return {"nodes": out, "rootOrder": root_order, "links": links}


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/state")
def get_state():
    return jsonify(build_state())


@app.post("/api/nodes")
def add_node():
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Message text is required."}), 400
    parent_id = d.get("parentId")
    author = (d.get("author") or "Anonymous").strip() or "Anonymous"

    depth = 0
    if parent_id:
        parent = Node.query.get(parent_id)
        if not parent:
            return jsonify({"error": "Parent message not found."}), 404
        depth = parent.depth + 1

    siblings = Node.query.filter(Node.parent_id == parent_id).all()
    position = (max([s.position for s in siblings]) + 1) if siblings else 0

    node = Node(id=new_id(), text=text, author=author, parent_id=parent_id,
                depth=depth, position=position, created_at=now())
    db.session.add(node)
    db.session.commit()
    return jsonify(build_state())


@app.patch("/api/nodes/<nid>")
def edit_node(nid):
    node = Node.query.get(nid)
    if not node:
        return jsonify({"error": "Message not found."}), 404
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    if text:
        node.text = text
        db.session.commit()
    return jsonify(build_state())


@app.delete("/api/nodes/<nid>")
def delete_node(nid):
    node = Node.query.get(nid)
    if not node:
        return jsonify(build_state())
    # collect node + all descendants
    to_delete = []
    stack = [nid]
    while stack:
        cur = stack.pop()
        to_delete.append(cur)
        stack.extend([c.id for c in Node.query.filter(Node.parent_id == cur).all()])
    for x in to_delete:
        Node.query.filter(Node.id == x).delete()
    # drop links touching any deleted node
    Link.query.filter(Link.a_id.in_(to_delete)).delete(synchronize_session=False)
    Link.query.filter(Link.b_id.in_(to_delete)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify(build_state())


@app.post("/api/links")
def add_link():
    d = request.get_json(force=True)
    a, b = d.get("a"), d.get("b")
    if not a or not b or a == b:
        return jsonify({"error": "Two different messages are required."}), 400
    exists = Link.query.filter(
        ((Link.a_id == a) & (Link.b_id == b)) | ((Link.a_id == b) & (Link.b_id == a))
    ).first()
    if exists:
        return jsonify(build_state())
    link = Link(id=new_id(), a_id=a, b_id=b,
                reporter=(d.get("reporter") or "Anonymous").strip() or "Anonymous",
                created_at=now(), status="open")
    db.session.add(link)
    db.session.commit()
    return jsonify(build_state())


@app.patch("/api/links/<lid>")
def update_link(lid):
    link = Link.query.get(lid)
    if not link:
        return jsonify({"error": "Contradiction not found."}), 404
    d = request.get_json(force=True)
    status = d.get("status")
    if status == "resolved":
        link.status = "resolved"
        link.res_text = (d.get("text") or "").strip()
        link.res_verdict = d.get("verdict")
        link.resolver = (d.get("resolver") or "Anonymous").strip() or "Anonymous"
        link.resolved_at = now()
    elif status == "open":
        link.status = "open"
        link.res_text = None
        link.res_verdict = None
        link.resolver = None
        link.resolved_at = None
    db.session.commit()
    return jsonify(build_state())


@app.delete("/api/links/<lid>")
def delete_link(lid):
    Link.query.filter(Link.id == lid).delete()
    db.session.commit()
    return jsonify(build_state())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
