from database import db
from datetime import datetime

class Flower(db.Model):
    __tablename__ = "flowers"
    id = db.Column(db.Integer , primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

    orders = db.relationship('Order', back_populates='flower')

class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer , primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(20), nullable=False)

    orders = db.relationship('Order', back_populates='customer')

class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer , primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    flower_id = db.Column(db.Integer, db.ForeignKey('flowers.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="completed") 

    customer = db.relationship('Customer', back_populates='orders')
    flower = db.relationship('Flower', back_populates='orders')


class ChatHistory(db.Model):
    __tablename__ = "chat_history"
    id         = db.Column(db.Integer, primary_key=True)
    role       = db.Column(db.String(20), nullable=False)   
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)