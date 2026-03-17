from database import db
from sqlalchemy import text as sa_text

def get_report_data():
    """Use raw SQL, process results as tuples."""
    
    # Revenue by flower
    revenue = db.session.execute(sa_text("""
        SELECT f.name,
               ROUND(SUM(o.total_price)::numeric, 2) AS revenue,
               SUM(o.quantity) AS units_sold
        FROM orders o
        JOIN flowers f ON o.flower_id = f.id
        GROUP BY f.name
        ORDER BY revenue DESC
    """)).fetchall()
    
    # Stock levels
    stock = db.session.execute(sa_text("""
        SELECT name, quantity, price
        FROM flowers
        ORDER BY quantity ASC
    """)).fetchall()
    
    # Status counts
    status = db.session.execute(sa_text("""
        SELECT status, COUNT(*) AS count
        FROM orders
        GROUP BY status
    """)).fetchall()
    
    # Top customers
    customers = db.session.execute(sa_text("""
        SELECT c.name,
               COUNT(o.id) AS total_orders,
               ROUND(COALESCE(SUM(o.total_price), 0)::numeric, 2) AS total_spent
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id
        GROUP BY c.id, c.name
        ORDER BY total_spent DESC
    """)).fetchall()
    
    # Summary stats
    summary = db.session.execute(sa_text("""
        SELECT 
            ROUND(COALESCE(SUM(total_price), 0)::numeric, 2) AS total_revenue,
            COUNT(*) AS total_orders,
            (SELECT COUNT(DISTINCT customer_id) FROM orders) AS total_customers,
            (SELECT COUNT(*) FROM flowers WHERE quantity < 20) AS low_stock_count
        FROM orders
    """)).fetchone()
    
    return {
        'revenue': revenue,
        'stock': stock,
        'status': status,
        'customers': customers,
        'summary': {
            'total_revenue': float(summary[0]) if summary[0] else 0,
            'total_orders': int(summary[1]) if summary[1] else 0,
            'total_customers': int(summary[2]) if summary[2] else 0,
            'low_stock_count': int(summary[3]) if summary[3] else 0,
        }
    }