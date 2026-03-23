import os
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask import Flask, render_template, jsonify, request, make_response
from database import db
from models import Flower, Customer, Order , ChatHistory
from sqlalchemy import text as sa_text
from chatbotgroq import get_chat_response, reset_daily_tokens
from report_data import get_report_data
from report_charts import generate_report
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
db.init_app(app)   
migrate = Migrate(app,db)

with app.app_context():
    db.create_all()

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"]
    response_data = get_chat_response(user_message)
    return jsonify(response_data)


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
    return jsonify({"message": "Flower added successfully!"})


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
    return jsonify({"message": "Order recorded!"})


@app.route("/add_customer", methods=["POST"])
def add_customer():
    data = request.get_json()
    new_customer = Customer(name=data["name"], email=data["email"], phone=data["phone"])
    db.session.add(new_customer)
    db.session.commit()
    return jsonify({"message": "Customer added successfully!"})


@app.route("/history", methods=["GET"])
def get_history():
    messages = ChatHistory.query.order_by(ChatHistory.created_at.asc()).all()
    return jsonify([
        {"role": m.role, "content": m.content}
        for m in messages
    ])


@app.route("/clear_history", methods=["POST"])
def clear_history():
    ChatHistory.query.delete()
    db.session.commit()
    return jsonify({"message": "Chat history cleared!"})


@app.route("/reset_tokens", methods=["POST"])
def reset_tokens():
    """Debug endpoint to reset token counter (development only)"""
    success = reset_daily_tokens()
    return jsonify({
        "message": "Token log reset" if success else "Failed to reset token log",
        "success": success
    })


@app.route("/download_report", methods=["GET"])
def download_report():
    try:
        data = get_report_data()        
        buf = generate_report(data)
        filename = f"report_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.png"
        response = make_response(buf.read())
        buf.close()
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-Type"] = "image/png"
        return response
    except Exception as e:  
        return jsonify({"error": str(e)})
    
if __name__ == "__main__":
    app.run(debug=True)
