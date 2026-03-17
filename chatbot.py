import os
import time
from database import db
from sqlalchemy import text
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))

SCHEMA = """
CREATE TABLE flowers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    price FLOAT NOT NULL
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    flower_id INTEGER REFERENCES flowers(id),
    quantity INTEGER NOT NULL,
    total_price FLOAT NOT NULL,
    order_date TIMESTAMP DEFAULT NOW()
);
"""


def generate_sql(user_question):
    prompt = f"""
    You are a PostgreSQL expert.
    Given this database schema:
    {SCHEMA}

    Convert this question to a valid PostgreSQL SELECT query:
    "{user_question}"

    Rules:
    - Return ONLY the SQL query, nothing else
    - No explanations, no markdown, no backticks
    - Only SELECT queries, never DELETE or UPDATE
    - Use proper JOINs when needed
    - Use LOWER() for name comparisons
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents = prompt
        )
    sql = response.text.strip()

    sql = sql.replace("```sql", "").replace("```", "").strip()
    print(f"Generated SQL: {sql}")
    return sql


def run_sql(sql):
    try:
        if not sql.strip().lower().startswith("select"):
            return None, "Only SELECT queries are allowed."

        result  = db.session.execute(text(sql))
        rows    = result.fetchall()
        columns = list(result.keys())
        data    = [dict(zip(columns, row)) for row in rows]
        return data, None

    except Exception as e:
        db.session.rollback()
        print(f"SQL Error: {e}")
        return None, str(e)
    

def generate_description(user_question, data_str):
    prompt = f"""
    You are a friendly flower shop assistant reporting to the owner.
    Reply in a friendly and professional way.
    The owner asked: "{user_question}"
    The database returned this data:
    {data_str}

    Write a brief and clear description of this result in 2-3 sentences.
    If data is empty or not relevant to a DB query, reply as a 
    friendly assistant and mention you can help with sales, 
    stock, orders and customers.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        content = prompt)
    return response.text.strip() 


def get_chat_response(user_question):
    # try:
    sql = generate_sql(user_question)
    time.sleep(20)
    data, error = run_sql(sql)

    if error or not data:
        data_str = "No data found."
    else:
        data_str = "\n".join(
            [", ".join(f"{k}: {v}" for k, v in row.items()) for row in data]
        )
    time.sleep(20)    

    description = generate_description(user_question, data_str)
    return description   
    
    # except Exception as e:
    #     if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
    #         return "API quota exceeded. Please try again in a few minutes or check your Gemini API plan."
    #     return f"Something went wrong: {str(e)}"


