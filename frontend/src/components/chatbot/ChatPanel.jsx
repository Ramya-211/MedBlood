import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, X, Trash2 } from "lucide-react";
import ChatMessage from "./ChatMessage";
import * as chatbotApi from "../../api/chatbot";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../context/AuthContext";

const SUGGESTIONS_BY_ROLE = {
  PHARMACIST: ["Which medicines have low stock?", "Which medicines are near expiry?",
    "What is the predicted demand for MED001?", "Show critical medicine alerts"],
  BLOOD_STAFF: ["Which blood groups are low in stock?", "Which blood is near expiry?",
    "What is the predicted O positive demand?", "Show critical blood alerts"],
  ADMIN: ["Which medicines have low stock?", "Which blood groups are low in stock?"],
};

export default function ChatPanel({ onClose }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hello! I can help with medicine and blood demand, inventory, forecasts, expiry, alerts and recommendations. What would you like to know?" },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [messages, sending]);

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setInput("");
    setSending(true);
    try {
      const res = await chatbotApi.sendMessage(msg, conversationId);
      setConversationId(res.conversation_id);
      setMessages((m) => [...m, { role: "assistant", content: res.message, intent: res.intent }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: apiErrorMessage(err, "I couldn't process that just now. Please try again.") }]);
    } finally {
      setSending(false);
    }
  };

  const clear = () => {
    setMessages([{ role: "assistant", content: "Conversation cleared. What would you like to know?" }]);
    setConversationId(null);
  };

  const suggestions = SUGGESTIONS_BY_ROLE[user?.role] || [];

  return (
    <div className="chat-panel fade-in">
      <div className="chat-panel-header">
        <div className="row gap-2">
          <div className="chat-avatar chat-avatar-ai"><Sparkles size={14} /></div>
          <div className="stack gap-0">
            <span className="text-h2" style={{ fontSize: 15 }}>AI Resource Assistant</span>
            <span className="text-micro">Data-grounded medicine & blood intelligence</span>
          </div>
        </div>
        <div className="row gap-1">
          <button className="btn btn-ghost btn-sm" onClick={clear} title="Clear conversation"><Trash2 size={15} /></button>
          <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={17} /></button>
        </div>
      </div>

      <div className="chat-messages" ref={scrollRef}>
        {messages.map((m, i) => <ChatMessage key={i} {...m} />)}
        {sending && (
          <div className="chat-row">
            <div className="chat-avatar chat-avatar-ai"><Sparkles size={13} /></div>
            <div className="chat-bubble chat-bubble-ai chat-typing"><span /><span /><span /></div>
          </div>
        )}
      </div>

      {messages.length <= 1 && suggestions.length > 0 && (
        <div className="chat-suggestions">
          {suggestions.map((s) => (
            <button key={s} className="chat-suggestion-chip" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
      )}

      <form className="chat-input-row" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input className="input grow" placeholder="Ask about inventory, demand, forecasts..." value={input}
          onChange={(e) => setInput(e.target.value)} disabled={sending} />
        <button type="submit" className="btn btn-primary" disabled={sending || !input.trim()}><Send size={15} /></button>
      </form>
    </div>
  );
}
