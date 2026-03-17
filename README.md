# Flower Shop Chatbot & Reporting System

A Flask-based web application that combines an AI-powered chatbot assistant with business intelligence reporting for a flower shop. The system tracks sales, inventory, customers, and generates visual reports.

## Features

- 🤖 **AI Chatbot Assistant** - Ask questions about sales, stock, and orders
- 📊 **Business Reports** - Generate PNG charts with revenue, stock levels, customer data
- 📈 **Analytics Dashboard** - View key metrics (total revenue, orders, customers, low stock)
- 💾 **PostgreSQL Database** - Persistent storage for flowers, customers, and orders
- 🔄 **Database Migrations** - Using Flask-Migrate with Alembic
- 📥 **Download Reports** - Export business data as PNG visualizations

## Tech Stack

- **Backend:** Flask, SQLAlchemy, Flask-Migrate
- **Database:** PostgreSQL
- **Visualization:** Matplotlib
- **AI:** Groq API (chatbot)
- **Frontend:** HTML, CSS, JavaScript
- **Python Version:** 3.8+

## Prerequisites

- Python 3.8 or higher
- PostgreSQL installed and running
- pip (Python package manager)
- Git (optional, for version control)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-username/flower-shop.git
cd flower-shop
```

### 2. Create a virtual environment
```bash
python -m venv venv
```

Activate it:
- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```bash
  source venv/bin/activate
  ```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create a PostgreSQL database
```sql
CREATE DATABASE flower_shop;
```

### 5. Configure environment variables

Create a `.env` file in the root directory:
```env
DATABASE_URL=postgresql://username:password@localhost:5432/flower_shop
GROQ_API_KEY=your-groq-api-key-here
FLASK_ENV=development
```

**Get your Groq API key:** https://console.groq.com/

### 6. Initialize the database
```bash
flask db upgrade
```

Or if it's a fresh setup:
```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### 7. Run the application
```bash
python app.py
```

The app will be available at: `http://localhost:5000`

## Project Structure

```
WEEK6/
├── app.py                 # Main Flask application
├── models.py              # Database models (Flower, Customer, Order, ChatHistory)
├── database.py            # Database configuration
├── report_data.py         # Fetch report data from PostgreSQL
├── report_charts.py       # Generate PNG charts using Matplotlib
├── chatbotgroq.py         # Groq API chatbot integration
├── prompts.py             # Chatbot prompts/instructions
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not in git)
├── .gitignore             # Git ignore file
│
├── static/
│   ├── style.css          # Frontend styles
│   └── script.js          # Frontend JavaScript
│
├── templates/
│   └── home.html          # Main HTML template
│
└── migrations/            # Database migration files
    ├── alembic.ini
    ├── env.py
    ├── script.py.mako
    └── versions/
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Home page (chatbot UI) |
| POST | `/chat` | Send message to chatbot |
| GET | `/report` | Get report JSON data |
| GET | `/history` | Get chat history |
| POST | `/clear_history` | Clear chat history |
| POST | `/add_flower` | Add a new flower |
| POST | `/add_order` | Record a new order |
| POST | `/add_customer` | Add a new customer |
| GET | `/download_report` | Download report as PNG |

## Usage Examples

### Add a Flower
```bash
curl -X POST http://localhost:5000/add_flower \
  -H "Content-Type: application/json" \
  -d '{"name": "Rose", "quantity": 50, "price": 5.99}'
```

### Add a Customer
```bash
curl -X POST http://localhost:5000/add_customer \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "phone": "+1234567890"}'
```

### Add an Order
```bash
curl -X POST http://localhost:5000/add_order \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "flower_id": 1, "quantity": 10, "total_price": 59.90}'
```

### Chat with Bot
```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the total revenue?"}'
```

### Download Report
```bash
# Downloads PNG file
curl http://localhost:5000/download_report > report.png
```

## Database Models

### Flower
- `id` (Primary Key)
- `name` (String)
- `quantity` (Integer)
- `price` (Float)

### Customer
- `id` (Primary Key)
- `name` (String)
- `email` (String, Unique)
- `phone` (String)

### Order
- `id` (Primary Key)
- `customer_id` (Foreign Key)
- `flower_id` (Foreign Key)
- `quantity` (Integer)
- `total_price` (Float)
- `order_date` (DateTime)
- `status` (String)

### ChatHistory
- `id` (Primary Key)
- `role` (String) - "user" or "bot"
- `content` (Text)
- `created_at` (DateTime)

## Report Features

The `/download_report` endpoint generates a PNG with:
- **Summary Statistics:** Total revenue, total orders, customer count, low stock count
- **Revenue by Flower:** Bar chart showing revenue per flower type
- **Stock Levels:** Horizontal bar chart with color coding (green ≥20, red <20)
- **Order Status:** Pie chart showing order status distribution
- **Top Customers:** Top 8 customers by total spend

## Troubleshooting

### "DATABASE_URL not found"
- Create a `.env` file with `DATABASE_URL` variable
- Restart the Flask application

### "GROQ_API_KEY not found"
- Add `GROQ_API_KEY` to your `.env` file
- Get key from: https://console.groq.com/

### PostgreSQL connection error
- Ensure PostgreSQL is running
- Check DATABASE_URL format: `postgresql://user:password@localhost:5432/dbname`

### Chart not generating
- Ensure matplotlib is installed: `pip install matplotlib`
- Verify database has data (add flowers, orders first)

## Development

### Run in debug mode
```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

### Create a new database migration
```bash
flask db migrate -m "Description of changes"
flask db upgrade
```

### View database
```bash
psql -U username -d flower_shop
```

## Dependencies

See `requirements.txt` for all packages. Main ones:
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- SQLAlchemy
- psycopg2
- python-dotenv
- matplotlib
- groq

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -m "Add feature"`
3. Push to branch: `git push origin feature/your-feature`
4. Open a Pull Request

## License

MIT License - feel free to use this project

## Support

For issues or questions, please create an issue in the repository.

---

**Happy Coding! 🌸**
