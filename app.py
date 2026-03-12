import os
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request
from database import db
from models import Flower, Customer, Order
from sqlalchemy import text as sa_text
#from chatbot import get_chat_response
from chatbotgroq import get_chat_response

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
db.init_app(app)   

with app.app_context():
    db.create_all()

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"]
    reply = get_chat_response(user_message)
    return jsonify({"reply": reply})


@app.route("/report", methods=["GET"])
def report():
    flowers       = Flower.query.all()
    total_revenue = sum(o.total_price for o in Order.query.all())
    top_flower    = db.session.execute(sa_text("""
        SELECT flowers.name, SUM(orders.quantity) as total
        FROM flowers
        JOIN orders ON flowers.id = orders.flower_id
        GROUP BY flowers.name
        ORDER BY total DESC
        LIMIT 1
    """)).fetchone()

    return jsonify({
        "total_flowers":      len(flowers),
        "total_revenue":      round(total_revenue, 2),
        "top_selling_flower": top_flower[0] if top_flower else "N/A",
        "flowers": [{"name": f.name, "quantity": f.quantity, "price": f.price} for f in flowers]
    })


@app.route("/add_flower", methods=["POST"])
def add_flower():
    data = request.get_json()
    new_flower = Flower(name=data["name"], quantity=data["quantity"], price=data["price"])
    db.session.add(new_flower)
    db.session.commit()
    return jsonify({"message": "Flower added successfully!"}), 201


@app.route("/add_order", methods=["POST"])
def add_order():
    data = request.get_json()
    new_order = Order(
        customer_id=data["customer_id"],
        flower_id=data["flower_id"],
        quantity=data["quantity"],
        total_price=data["total_price"]
    )
    db.session.add(new_order)
    db.session.commit()
    return jsonify({"message": "Order recorded!"}), 201


@app.route("/add_customer", methods=["POST"])
def add_customer():
    data = request.get_json()
    new_customer = Customer(name=data["name"], email=data["email"], phone=data["phone"])
    db.session.add(new_customer)
    db.session.commit()
    return jsonify({"message": "Customer added successfully!"}), 201


if __name__ == "__main__":
    app.run(debug=True)