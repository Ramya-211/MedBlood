import client from "./client";

export const listUsers = (params) => client.get("/api/admin/users", { params }).then((r) => r.data);
export const createUser = (body) => client.post("/api/admin/users", body).then((r) => r.data);
export const updateUser = (id, body) => client.patch(`/api/admin/users/${id}`, body).then((r) => r.data);

export const getDashboard = () => client.get("/api/admin/dashboard").then((r) => r.data);
