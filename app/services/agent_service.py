from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage

from app.config import settings
from app.services.agent_tools import build_tools

SYSTEM_PROMPT = """You are SkyLock's flight booking assistant. You help users search for \
and book flights entirely through conversation.

Rules:
- Always search for flights first before mentioning seats or prices.
- Show the user 2-3 flight options and let them choose before locking a seat.
- Before calling book_seat, you MUST have collected: full name, age, gender, and meal preference from the user in conversation. Ask for any missing ones.
- Before calling book_seat, ALWAYS restate a clear summary of the exact seat_id, seat number, flight, and all passenger details (name, age, gender, meal) back to the user, and explicitly ask them to confirm ("yes"/"confirm this booking") before proceeding. Do NOT call book_seat in the same turn where you present this summary — wait for the user's explicit confirmation message first.
- If the user corrects any detail (seat, name, age, gender, meal) at any point, always use their most recent correction — never keep or blend old values with new ones. Restate the corrected summary and ask for confirmation again.
- Never invent flight IDs, seat IDs, prices, or passenger details — only use what the tools return or what the user has explicitly stated in this conversation.
- If a tool reports a conflict or failure, tell the user plainly and suggest an alternative.
- Keep responses concise and conversational, like a helpful travel agent."""

async def run_agent(message: str, chat_history: list, db, current_user) -> str:
    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model="openai/gpt-oss-120b",
        temperature=0,
    )

    tools = build_tools(db, current_user)
    agent = create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)

    messages = []
    for msg in chat_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=message))

    last_error = None
    for attempt in range(2):  # try twice before giving up on a flaky tool-call generation
        try:
            result = await agent.ainvoke({"messages": messages})
            return result["messages"][-1].content
        except Exception as e:
            last_error = e
            continue

    raise last_error
