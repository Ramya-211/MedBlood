import { Sparkles } from "lucide-react";

export default function ChatMessage({ role, content, intent }) {
  const isUser = role === "user";
  return (
    <div className={`chat-row ${isUser ? "chat-row-user" : ""} fade-in`}>
      {!isUser && <div className="chat-avatar chat-avatar-ai"><Sparkles size={13} /></div>}
      <div className={`chat-bubble ${isUser ? "chat-bubble-user" : "chat-bubble-ai"}`}>
        {content}
        {intent && !isUser && intent !== "chitchat" && (
          <div className="chat-intent-tag">{intent.replace(/_/g, " ")}</div>
        )}
      </div>
    </div>
  );
}
