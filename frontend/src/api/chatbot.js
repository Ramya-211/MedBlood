import client from "./client";

export const sendMessage = (message, conversationId) =>
  client.post("/api/chatbot/query", { message, conversation_id: conversationId || null }).then((r) => r.data);

export const getHistory = (conversationId) =>
  client.get(`/api/chatbot/history/${conversationId}`).then((r) => r.data);
