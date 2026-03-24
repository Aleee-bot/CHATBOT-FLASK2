import json
import re
from datetime import datetime
from groq import RateLimitError, APIConnectionError  
from database import db
from sqlalchemy import text
from dotenv import load_dotenv
from models import ChatHistory
from prompts import SYSTEM_PROMPT, SQL_PROMPT, SCHEMA
from dynamic_charts import extract_chart_type_from_input, generate_chart_with_type, buffer_to_base64
from langchain_groq import ChatGroq  
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

load_dotenv()

llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.7)

MAX_HISTORY_EXCHANGES = 10
TOKEN_LOG_FILE = "token_usage_log.json"  


def extract_dates_from_text(text: str) -> list:
    dates_found = []
    
    month_pattern = r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2}(?:,?\s*\d{4})?'
    matches = re.findall(month_pattern, text, re.IGNORECASE)
    dates_found.extend(matches)
    
    num_date_pattern = r'\d{1,4}[-/]\d{1,2}[-/]\d{1,4}'
    matches = re.findall(num_date_pattern, text)
    dates_found.extend(matches)
    
    day_month_pattern = r'\d{1,2}\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)(?:\s+\d{4})?'
    matches = re.findall(day_month_pattern, text, re.IGNORECASE)
    dates_found.extend(matches)
    
    month_year_pattern = r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{4}'
    matches = re.findall(month_year_pattern, text, re.IGNORECASE)
    dates_found.extend(matches)
    
    year_pattern = r'\b(20\d{2}|19\d{2})\b'
    matches = re.findall(year_pattern, text)
    dates_found.extend(matches)
    
    relative_pattern = r'(today|tomorrow|yesterday|last\s+week|last\s+month|this\s+week|this\s+month|next\s+week|next\s+month)'
    matches = re.findall(relative_pattern, text, re.IGNORECASE)
    dates_found.extend(matches)
    
    seen = set()
    unique_dates = []
    for date in dates_found:
        if date.lower() not in seen:
            seen.add(date.lower())
            unique_dates.append(date)
    
    return unique_dates


def load_history():
    rows = (
        ChatHistory.query
        .order_by(ChatHistory.created_at.asc())
        .limit(MAX_HISTORY_EXCHANGES * 2)   
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def extract_conversation_context(history: list) -> dict:
    context = {
        'recent_exchanges': [],
        'last_user_message': None,
        'last_assistant_message': None,
        'context_summary': "",
        'established_facts': [],
        'mentioned_dates': []
    }
    
    try:
        FACT_KEYWORDS = {
            'valentine': ['valentine', 'feb 14', 'february 14'],
            'christmas': ['christmas', 'dec 25', 'december 25'],
            'new year': ['new year', 'jan 1', 'january 1'],
            'easter': ['easter'],
        }
        
        facts_found = set()
        all_dates_mentioned = set()
        
        for msg in history:
            content_lower = msg['content'].lower()
            
            for fact_name, keywords in FACT_KEYWORDS.items():
                if any(kw in content_lower for kw in keywords):
                    if fact_name not in facts_found:
                        facts_found.add(fact_name)
                        if 'valentine' in fact_name.lower():
                            context['established_facts'].append("Valentine's Day is February 14")
                        elif 'christmas' in fact_name.lower():
                            context['established_facts'].append("Christmas is December 25")
                        elif 'new year' in fact_name.lower():
                            context['established_facts'].append("New Year is January 1")
            
            dates = extract_dates_from_text(msg['content'])
            for date in dates:
                all_dates_mentioned.add(date)
        
        context['mentioned_dates'] = sorted(list(all_dates_mentioned))
        
        RECENT_EXCHANGES = 5
        recent_messages = history[-(RECENT_EXCHANGES * 2):] if len(history) > 0 else []
        
        for i in range(0, len(recent_messages), 2):
            if i + 1 < len(recent_messages):
                user_msg = recent_messages[i]
                assistant_msg = recent_messages[i + 1]
                
                if user_msg['role'] == 'user' and assistant_msg['role'] == 'assistant':
                    exchange = {
                        'user': user_msg['content'][:100], 
                        'assistant': assistant_msg['content'][:100]
                    }
                    context['recent_exchanges'].append(exchange)
                    context['last_user_message'] = user_msg['content']
                    context['last_assistant_message'] = assistant_msg['content']
        
        if context['recent_exchanges']:
            last_exchange = context['recent_exchanges'][-1]
            context['context_summary'] = f"Recent: User asked about '{last_exchange['user'][:50]}...'"
        
    except Exception as e:
        print(f"[WARNING] Could not extract context: {e}")
    
    return context


def save_message(role, content):
    """Persist a single message to the chat_history table.
    
    WHY: Build conversation history for context & audit trail
    """
    msg = ChatHistory(role=role, content=content)
    db.session.add(msg)
    db.session.commit()


def clear_history():
    """Wipe all chat history — useful for starting a fresh session.
    
    WHY: Allow users to reset conversation context when needed
    """
    ChatHistory.query.delete()
    db.session.commit()


def reset_daily_tokens():
    """Clear token logs for development/testing.
    
    WHY: Reset token counter during development
         Use this after you've exceeded the quota for the day
    """
    try:
        import os
        if os.path.exists(TOKEN_LOG_FILE):
            os.remove(TOKEN_LOG_FILE)
        print(f"[DEBUG] Token log cleared: {TOKEN_LOG_FILE}")
        return True
    except Exception as e:
        print(f"[ERROR] Could not clear token log: {e}")
        return False


def log_token_usage(function_name, token_data, user_input="", success=True):
    """Log token usage to file for monitoring and analysis.
    
    WHY: Track token consumption patterns to optimize costs and 
         identify bottlenecks in the system
    
    Args:
        function_name: Which function consumed tokens
        token_data: Dict with input_tokens, output_tokens, total_tokens
        user_input: What user asked (for context)
        success: Whether the operation succeeded
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "function": function_name,
        "input_tokens": token_data.get("input_tokens", 0),
        "output_tokens": token_data.get("output_tokens", 0),
        "total_tokens": token_data.get("total_tokens", 0),
        "user_input": user_input[:50] if user_input else "",
        "success": success
    }
    
    try:
        with open(TOKEN_LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[WARNING] Could not log tokens: {e}")


def get_daily_token_usage():
    """Calculate total tokens used today for quota checking.
    WHY: Prevent going over daily/monthly token limits before API blocks us
    """
    today = datetime.now().date()
    total = 0
    
    try:
        with open(TOKEN_LOG_FILE, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry_date = datetime.fromisoformat(entry["timestamp"]).date()
                    if entry_date == today and entry.get("success"):
                        total += entry.get("total_tokens", 0)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    
    return total


def handle_greeting(user_question: str):
    """Handle simple greetings WITHOUT calling LLM.
    
    WHY: 
    - Greetings are predictable → no need for LLM
    - Each greeting saves ~200 tokens
    - Ensures consistency (same greeting = same response)
    - Faster response time
    
    Returns:
        Tuple of (response_text, token_data) or (None, None) if not a greeting
    """
    q_lower = user_question.strip().lower()
    
    greeting_responses = {
        "hi": "Hi there! How can I help with your flower shop today?",
        "hello": "Hello! What can I assist you with?",
        "hey": "Hey! What do you need?",
        "how are you": "I'm doing well, thanks for asking! How can I help?",
        "how are you?": "I'm doing well, thanks for asking! How can I help?",
        "thanks": "You're welcome! Anything else I can help with?",
        "thank you": "You're welcome! Let me know if you need anything.",
        "bye": "Goodbye! Have a great day!",
        "goodbye": "Goodbye! Take care!",
        "what can you do": "I can help with: Sales reports, Inventory levels, Order tracking, and Customer insights. What would you like?",
    }
    
    if q_lower in greeting_responses:
        print(f"[GREETING] Matched exactly: {q_lower}")
        return greeting_responses[q_lower], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    

    for greeting, response in greeting_responses.items():
        if greeting in q_lower and len(greeting) > 2: 
            print(f"[GREETING] Matched partially: {greeting} in {q_lower}")
            return response, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    return None, None 


def needs_sql_query(user_question: str, history: list) -> bool:
    """Quickly check if question needs database query.
    
    WHY: 
    - Avoid unnecessary SQL generation (saves ~500 tokens)
    - Many questions can be answered without DB access
    - Improves response speed
    
    Returns: True if SQL query likely needed, False otherwise
    """
    sql_keywords = [
        "show", "get", "list", "find", "select", "display", 
        "give me", "how many", "total", "count", "what is", "which",
        "report", "revenue", "sales", "orders", "customers", "inventory",
        "stock", "available", "sold", "purchased", "top", "best",
        "most", "least", "when", "date"  
    ]
    
    q_lower = user_question.lower()
    
    if any(keyword in q_lower for keyword in sql_keywords):
        return True

    greetings = [
        "hi", "hello", "hey", "how are you", "thanks", "thank you",
        "bye", "goodbye", "what can you", "help me"
    ]
    if any(greeting in q_lower for greeting in greetings):
        return False
    
    return True


def call_llm(messages: list):
    try:
        lc_messages = []
        for msg in messages:
            if msg["role"] == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        
        response = llm.invoke(lc_messages)
        
        token_data = {
            "input_tokens": response.usage_metadata.get("input_tokens", 0),
            "output_tokens": response.usage_metadata.get("output_tokens", 0),
            "total_tokens": response.usage_metadata.get("input_tokens", 0) + 
                           response.usage_metadata.get("output_tokens", 0)
        }
        
        return response.content.strip(), token_data
    
    except RateLimitError as e:
        print(f"[ERROR] Rate limit hit: {e}")
        return "⚠️ API quota exceeded. Please try again later.", {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
        }
    
    except APIConnectionError as e:
        print(f"[ERROR] Connection failed: {e}")
        return "⚠️ Connection error. Please try again.", {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
        }
    
    except Exception as e:
        print(f"[ERROR] Unexpected LLM error: {e}")
        return f"⚠️ Error occurred: {str(e)[:100]}", {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
        }


def generate_sql(user_question: str, history: list):
    """Generate SQL query from natural language question.
    
    WHY:
    - Converts user intent to database queries
    - Includes conversation context for pronouns/references AND established facts
    - Logs token usage for monitoring
    - Traces in LangSmith for debugging
    
    Returns: Tuple of (sql_string, token_data_dict)
    """
    context = extract_conversation_context(history)
    
    context_note = ""
    if context['context_summary'] or context['established_facts'] or context['mentioned_dates']:
        context_note = f"\n\nCONVERSATION CONTEXT:"
        if context['context_summary']:
            context_note += f"\nRecent: {context['context_summary']}"
        if context['established_facts']:
            context_note += f"\nEstablished facts: {' | '.join(context['established_facts'])}"
        if context['mentioned_dates']:
            context_note += f"\nDates mentioned in conversation: {', '.join(context['mentioned_dates'][:10])}"
            context_note += "\nUse these date references to understand what period the user is asking about."
        context_note += f"\nUser's last message: {context['last_user_message'][:150] if context['last_user_message'] else 'N/A'}"
        context_note += "\nIf the user uses event names or vague time references without exact dates, use the context above."
    
    prompt = SQL_PROMPT.format(schema=SCHEMA, question=user_question)
    prompt += context_note
    
    messages = [SYSTEM_PROMPT] + history + [{"role": "user", "content": prompt}]
    sql, token_data = call_llm(messages)
    
    sql = sql.replace("```sql", "").replace("```", "").strip()
    
    print(f"[SQL] {sql}")
    print(f"[CONTEXT] {context['context_summary']}")
    print(f"[TOKENS] Input: {token_data['input_tokens']}, Output: {token_data['output_tokens']}")
    
    # Validate SQL syntax
    if sql and sql.upper() != "NOT_SQL" and sql.lower().startswith("select"):
        if "'%%" in sql or "%%'" in sql:
            print(f"[SQL WARNING] Double-escaped wildcards detected. Correcting...")
            sql = sql.replace("'%%", "'%").replace("%%'", "%'")
    
    log_token_usage("generate_sql", token_data, user_question, success=True)
    
    return sql, token_data


def run_sql(sql: str):
    try:
        if not sql.strip().lower().startswith("select"):
            return None, "Only SELECT queries are allowed."

        # Validate table existence
        allowed_tables = ["flowers", "customers", "orders", "chat_history"]
        sql_lower = sql.lower()
        if not any(table in sql_lower for table in allowed_tables):
            return None, "Query must reference valid tables: flowers, customers, or orders."

        print(f"[SQL DEBUG] Executing: {sql[:150]}...") 
        
        result = db.session.execute(text(sql))
        rows = result.fetchall()
        columns = list(result.keys())
        data = [dict(zip(columns, row)) for row in rows]
        
        print(f"[SQL DEBUG] ──────────────────────────")
        print(f"[SQL DEBUG] Query Status: ✅ SUCCESS")
        print(f"[SQL DEBUG] Columns: {columns}")
        print(f"[SQL DEBUG] Rows returned: {len(data)}")
        
        if len(data) > 0:
            print(f"[SQL DEBUG] Data preview:")
            for i, row in enumerate(data[:3]):  
                print(f"[SQL DEBUG]   Row {i+1}: {row}")
            if len(data) > 3:
                print(f"[SQL DEBUG]   ... and {len(data)-3} more rows")
        else:
            print(f"[SQL DEBUG] ⚠️  No data returned!")
        print(f"[SQL DEBUG] ──────────────────────────")
        
        return data, None

    except Exception as e:
        db.session.rollback()
        print(f"[SQL ERROR] Query failed: {e}")
        return None, str(e)        
    

def generate_response(user_question: str, data_str: str, history: list):

    context = extract_conversation_context(history)
    context_note = ""
    if context['context_summary'] or context['established_facts'] or context['mentioned_dates']:
        context_note = f"\n\nCONVERSATION CONTEXT:"
        if context['context_summary']:
            context_note += f"\n{context['context_summary']}"
        if context['established_facts']:
            context_note += f"\nEstablished facts: {' | '.join(context['established_facts'])}"
        if context['mentioned_dates']:
            context_note += f"\nDates mentioned: {', '.join(context['mentioned_dates'][:10])}"
    
    has_data = data_str and 'No database query needed' not in data_str and 'No data found' not in data_str
    
    if has_data:
        data_section = f"""DATABASE RESULTS (ACTUAL DATA):
{data_str}

You MUST reference the actual numbers above. Do not make up information."""
    else:
        data_section = """DATABASE RESULTS: No data found for this query.
You must inform the user that no records exist for their request."""
    
    prompt = f"""You are Flora, a flower shop assistant. Your response must be based STRICTLY on the provided data.

QUESTION: {user_question}

{data_section}

{context_note}

INSTRUCTIONS:
1. If data exists above → Summarize in 2-3 sentences using the ACTUAL numbers
2. If no data → Say: "I don't have any sales records for that period."
3. NEVER invent data, dates, or numbers not shown above
4. NEVER apologize excessively or say "our system is catching up"
5. Be direct and professional

Format numbers clearly: "We sold X units for $Y.Z total"
"""
    messages = [
        SYSTEM_PROMPT,  
        {"role": "user", "content": prompt}
    ]
    response, token_data = call_llm(messages)
    
    print(f"[RESPONSE] {len(response.split())} words | Data received: {data_str[:80]}...")
    print(f"[RESPONSE] Has actual data: {has_data}")
    
    log_token_usage("generate_response", token_data, user_question, success=True)
    
    return response, token_data


def detect_explicit_chart_request(user_message: str) -> bool:
    """
    Detect if user EXPLICITLY asked for a chart/visualization.
    
    WHY: Only ask for chart type if user really wants one.
         Don't trigger on generic data queries like "show sales".
         Only trigger on explicit requests like "show me a pie chart".
    
    Returns: True only if user mentioned chart/graph/visualization keywords
    """
    chart_keywords = [
        'chart', 'graph', 'plot', 'visualize', 'visualization',
        'visual report', 'show chart', 'display chart', 'create chart',
        'generate chart', 'draw', 'display graph', 'pie', 'bar', 
        'line chart', 'scatter', 'diagram', 'infographic'
    ]
    
    message_lower = user_message.lower()
    
    has_chart_keyword = any(kw in message_lower for kw in chart_keywords)
    
    simple_queries = ['show', 'get', 'display', 'list']
    is_simple_query_only = any(kw in message_lower for kw in simple_queries) and not has_chart_keyword
    
    return has_chart_keyword and not is_simple_query_only


def get_chat_response(user_question: str):
    try:
        daily_tokens = get_daily_token_usage()
        DAILY_QUOTA = 500000
        if daily_tokens > DAILY_QUOTA:
            warning = f"⚠️ Daily token quota ({DAILY_QUOTA}) exceeded. Used: {daily_tokens}"
            print(f"[WARNING] {warning}")
            return {
                "message": warning,
                "tokens": {"input": 0, "output": 0, "total": 0}
            }
        
        history = load_history()
        save_message("user", user_question)
        
        total_tokens = {"input": 0, "output": 0}

        q_lower = user_question.lower()
        write_keywords = [
            "delete", "remove", "drop", "erase", "update", "modify", 
            "edit", "change", "insert", "add new", "create new"
        ]
        
        if any(word in q_lower for word in write_keywords):
            reply = "I'm not able to modify data. I can only read and report. Please use your admin panel to make any changes."
            save_message("assistant", reply)
            return {"message": reply, "tokens": {"input": 0, "output": 0, "total": 0}}

        if detect_explicit_chart_request(user_question):
            print(f"[CHAT] Explicit chart request detected: {user_question}")
            
            user_chart_preference = extract_chart_type_from_input(user_question)
            print(f"[CHAT] User chart preference: {user_chart_preference}")
            
            if user_chart_preference:
                print(f"Chart is ready")
                buf, error = generate_chart_with_type(user_question, user_chart_preference)
                
                if error:
                    reply = f"Could not generate chart: {error}"
                    save_message("assistant", reply)
                    return {"message": reply, "tokens": {"input": 0, "output": 0, "total": 0}}
                
                image_base64 = buffer_to_base64(buf)
                reply = f"Here's your {user_chart_preference} chart!"
                save_message("assistant", reply)
                
                return {
                    "message": reply,
                    "chart": image_base64,
                    "tokens": {"input": 0, "output": 0, "total": 0}
                }
            else:
                reply = "What type of chart would you like? Choose one:\n• **pie** - Show proportions\n• **bar** - Compare values\n• **line** - Show trends\n• **scatter** - Show relationships"
                save_message("assistant", reply)
                
                return {
                    "message": reply,
                    "ask_for_chart": True,
                    "query": user_question,
                    "tokens": {"input": 0, "output": 0, "total": 0}
                }
        
        greeting_reply, _ = handle_greeting(user_question)
        if greeting_reply:
            save_message("assistant", greeting_reply)
            return {
                "message": greeting_reply,
                "tokens": {"input": 0, "output": 0, "total": 0}
            }
        
        if needs_sql_query(user_question, history):
            sql, sql_tokens = generate_sql(user_question, history)
            total_tokens["input"] += sql_tokens["input_tokens"]
            total_tokens["output"] += sql_tokens["output_tokens"]

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
        else:
            print("[CHAT] No SQL needed for this question")
            data_str = "No database query needed for this message."

        reply, response_tokens = generate_response(user_question, data_str, history)
        total_tokens["input"] += response_tokens["input_tokens"]
        total_tokens["output"] += response_tokens["output_tokens"]
        
        save_message("assistant", reply)
        
        return {
            "message": reply,
            "tokens": {
                "input": total_tokens["input"],
                "output": total_tokens["output"],
                "total": total_tokens["input"] + total_tokens["output"]
            }
        }
    

    except Exception as e:
        error_msg = f"Something went wrong: {str(e)}"
        print(f"[ERROR] {error_msg}")
        log_token_usage("get_chat_response", 
                       {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, 
                       user_question, 
                       success=False)
        return {
            "message": error_msg, 
            "tokens": {"input": 0, "output": 0, "total": 0}
        }