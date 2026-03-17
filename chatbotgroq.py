import os
from groq import Groq
from database import db
from sqlalchemy import text
from dotenv import load_dotenv
from models import ChatHistory
from prompts import SYSTEM_PROMPT , SQL_PROMPT , RESPONSE_PROMPT , SCHEMA

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MAX_HISTORY_EXCHANGES = 10

def load_history():
    """Load recent chat history from DB, ordered oldest first."""
    rows = (
        ChatHistory.query
        .order_by(ChatHistory.created_at.asc())
        .limit(MAX_HISTORY_EXCHANGES * 2)   
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def save_message(role, content):
    """Persist a single message to the chat_history table."""
    msg = ChatHistory(role=role, content=content)
    db.session.add(msg)
    db.session.commit()


def clear_history():
    """Wipe all chat history — useful for starting a fresh session."""
    ChatHistory.query.delete()
    db.session.commit()


def call_llm(messages):
    """
    Call Groq with a full message list.
    messages = [system_prompt] + history + [current_user_message]
    """
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages
    )
    return response.choices[0].message.content.strip()


def generate_sql(user_question, history):
    prompt = SQL_PROMPT.format(schema=SCHEMA, question=user_question)
    messages = [SYSTEM_PROMPT] + history + [{"role": "user", "content": prompt}]
    sql = call_llm(messages)
    sql = sql.replace("```sql", "").replace("```", "").strip()
    print(f"[SQL] {sql}")
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
        print(f"[SQL Error] {e}")
        return None, str(e)


def generate_response(user_question, data_str):
    prompt = RESPONSE_PROMPT.format(question=user_question, data=data_str)
    messages = [{"role": "user", "content": prompt}]
    return call_llm(messages)

WRITE_KEYWORDS = ["delete", "remove", "drop", "erase", "update", "modify", 
                  "edit", "change", "insert", "add new", "create new"]

def get_chat_response(user_question):
    try:
        history = load_history()
        save_message("user", user_question)

        q_lower = user_question.lower()
        if any(word in q_lower for word in WRITE_KEYWORDS):
            reply = "I'm not able to modify data. I can only read and report. Please use your admin panel to make any changes."
            save_message("assistant", reply)
            return reply

        sql = generate_sql(user_question, history)

        if sql.upper() == "NOT_SQL" or not sql.strip().lower().startswith("select"):
            data_str = "No database query needed for this message."
        else:
            data, error = run_sql(sql)
            if error or not data:
                data_str = "No data found or query returned an error."
            else:
                data_str = "\n".join(
                    [", ".join(f"{k}: {v}" for k, v in row.items()) for row in data]
                )
        reply = generate_response(user_question, data_str)
        save_message("assistant", reply)
        return reply

    except Exception as e:
        return f"Something went wrong: {str(e)}"
