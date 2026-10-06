import client from "./client";

export const login = (username, password) => client.post("/api/auth/login", { username, password }).then((r) => r.data);
export const logout = () => client.post("/api/auth/logout");
export const me = () => client.get("/api/auth/me").then((r) => r.data);
