 import { useEffect, useState } from "react";
import {
  UserPlus,
  Search,
  ShieldCheck,
  UserCheck,
  UserX,
  Pencil,
  Eye,
  EyeOff,
} from "lucide-react";
import PageHeader from "../../components/ui/PageHeader";
import Section from "../../components/ui/Section";
import DataTable from "../../components/ui/DataTable";
import StatusBadge from "../../components/ui/StatusBadge";
import ErrorState from "../../components/ui/ErrorState";
import Skeleton from "../../components/ui/Skeleton";
import * as adminApi from "../../api/admin";

const ROLES = ["PHARMACIST", "BLOOD_STAFF"];

const emptyForm = {
  username: "",
  full_name: "",
  password: "",
  role: "PHARMACIST",
  is_active: true,
};

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState(emptyForm);

  const [editingUser, setEditingUser] = useState(null);
  const [showEditForm, setShowEditForm] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const loadUsers = async () => {
    try {
      setLoading(true);
      setError("");

      const data = await adminApi.listUsers({
        search: search || undefined,
        role: roleFilter || undefined,
      });

      console.log(
        "ADMIN USERS API RESPONSE:",
        JSON.stringify(data, null, 2)
      );

      setUsers(data?.items || []);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Unable to load users."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, [roleFilter]);

  const handleCreate = async (e) => {
    e.preventDefault();

    try {
      setSaving(true);
      setError("");

      await adminApi.createUser({
        username: form.username,
        full_name: form.full_name,
        password: form.password,
        role: form.role,
      });

      setForm(emptyForm);
      setShowForm(false);

      await loadUsers();
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Unable to create user."
      );
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);

    setForm({
      username: user.username || "",
      full_name: user.full_name || "",
      password: "",
      role: user.role || "PHARMACIST",
      is_active: Boolean(user.is_active),
    });

    setShowPassword(false);
    setShowEditForm(true);
    setShowForm(false);
    setError("");
  };

  const handleUpdate = async (e) => {
  e.preventDefault();

  if (!editingUser) return;

  if (form.password && form.password.length < 8) {
    setError("Please enter the password with at least 8 characters.");
    return;
  }

  try {
    setSaving(true);
    setError("");

    const updateBody = {
      username: form.username,
      full_name: form.full_name,
      role: form.role,
      is_active: form.is_active,
    };

    if (form.password) {
      updateBody.new_password = form.password;
    }

    await adminApi.updateUser(editingUser.id, updateBody);

    setEditingUser(null);
    setShowEditForm(false);
    setForm(emptyForm);
    setShowPassword(false);

    await loadUsers();
  } catch (err) {
    setError(
      err?.response?.data?.detail ||
        "Unable to update user."
    );
  } finally {
    setSaving(false);
  }
};

  const closeEdit = () => {
    setEditingUser(null);
    setShowEditForm(false);
    setForm(emptyForm);
    setShowPassword(false);
  };

  const handleToggleStatus = async (user) => {
    const currentStatus =
      user.is_active ?? user.active ?? user.status === "ACTIVE";

    const action = currentStatus ? "deactivate" : "activate";

    if (
      !window.confirm(
        `Are you sure you want to ${action} ${user.username}?`
      )
    ) {
      return;
    }

    try {
      setError("");

      await adminApi.updateUser(user.id || user.user_id, {
        is_active: !currentStatus,
      });

      await loadUsers();
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          `Unable to ${action} user.`
      );
    }
  };

  const columns = [
    {
      key: "username",
      header: "Username",
      render: (user) => (
        <span style={{ fontWeight: 600 }}>{user.username}</span>
      ),
    },
    {
      key: "full_name",
      header: "Full Name",
      render: (user) => user.full_name || "—",
    },
    {
      key: "role",
      header: "Role",
      render: (user) => (
        <StatusBadge
          status={user.role?.replace("_", " ") || "Unknown"}
        />
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (user) => {
        const active =
          user.is_active ??
          user.active ??
          user.status === "ACTIVE";

        return (
          <StatusBadge
            status={active ? "Active" : "Inactive"}
          />
        );
      },
    },
    {
      key: "actions",
      header: "Actions",
      render: (user) => {
        const active =
          user.is_active ??
          user.active ??
          user.status === "ACTIVE";

        return (
          <div className="row gap-2">
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => handleEdit(user)}
            >
              <Pencil size={14} />
              Edit
            </button>

            <button
              className="btn btn-ghost btn-sm"
              onClick={() => handleToggleStatus(user)}
            >
              {active ? (
                <>
                  <UserX size={14} />
                  Deactivate
                </>
              ) : (
                <>
                  <UserCheck size={14} />
                  Activate
                </>
              )}
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="stack gap-6">
      <PageHeader
        title="User Management"
        subtitle="Manage system users, roles, and account access."
        onRefresh={loadUsers}
      />

      {error && (
        <ErrorState
          message={error}
          onRetry={loadUsers}
        />
      )}

      <Section>
        <div
          className="row-between"
          style={{ marginBottom: 16 }}
        >
          <div className="row gap-3">
            <div className="input-with-icon">
              <Search size={16} />

              <input
                className="input"
                placeholder="Search users..."
                value={search}
                onChange={(e) =>
                  setSearch(e.target.value)
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    loadUsers();
                  }
                }}
              />
            </div>

            <select
              className="input"
              value={roleFilter}
              onChange={(e) =>
                setRoleFilter(e.target.value)
              }
            >
              <option value="">All roles</option>

              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>

          <button
            className="btn btn-primary"
            onClick={() => {
              setShowForm((value) => !value);
              closeEdit();
            }}
          >
            <UserPlus size={16} />
            Add User
          </button>
        </div>

        {showEditForm && editingUser && (
          <form
            onSubmit={handleUpdate}
            className="card"
            style={{ marginBottom: 20 }}
          >
            <div className="stack gap-4">
              <div>
                <h3 style={{ margin: 0 }}>
                  Edit User
                </h3>

                <p
                  className="text-small"
                  style={{ marginTop: 4 }}
                >
                  Update account details and optionally
                  change the password.
                </p>
              </div>

              <div className="grid grid-cols-2">
                <label className="stack gap-1">
                  <span className="text-small">
                    Username
                  </span>

                  <input
                    className="input"
                    required
                    value={form.username}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        username: e.target.value,
                      })
                    }
                  />
                </label>

                <label className="stack gap-1">
                  <span className="text-small">
                    Full Name
                  </span>

                  <input
                    className="input"
                    required
                    value={form.full_name}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        full_name: e.target.value,
                      })
                    }
                  />
                </label>

                <label className="stack gap-1">
                  <span className="text-small">
                    Role
                  </span>

                  <select
                    className="input"
                    value={form.role}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        role: e.target.value,
                      })
                    }
                  >
                    {ROLES.map((role) => (
                      <option
                        key={role}
                        value={role}
                      >
                        {role.replace("_", " ")}
                      </option>
                    ))}

                    {editingUser.role === "ADMIN" && (
                      <option value="ADMIN">
                        ADMIN
                      </option>
                    )}
                  </select>
                </label>

                <label className="stack gap-1">
                  <span className="text-small">
                    Status
                  </span>

                  <select
                    className="input"
                    value={form.is_active ? "ACTIVE" : "INACTIVE"}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        is_active:
                          e.target.value === "ACTIVE",
                      })
                    }
                  >
                    <option value="ACTIVE">
                      Active
                    </option>

                    <option value="INACTIVE">
                      Inactive
                    </option>
                  </select>
                </label>

                <label
                  className="stack gap-1"
                  style={{ gridColumn: "1 / -1" }}
                >
                  <span className="text-small">
                    New Password
                  </span>

                  <div
                    className="input-with-icon"
                    style={{ position: "relative" }}
                  >
                    <input
                      className="input"
                      type={
                        showPassword
                          ? "text"
                          : "password"
                      }
                      placeholder="Leave blank to keep current password"
                      value={form.password}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          password: e.target.value,
                        })
                      }
                      style={{ paddingRight: 42 }}
                    />

                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setShowPassword(
                          (value) => !value
                        )
                      }
                      style={{
                        position: "absolute",
                        right: 4,
                        top: "50%",
                        transform:
                          "translateY(-50%)",
                      }}
                      aria-label={
                        showPassword
                          ? "Hide password"
                          : "Show password"
                      }
                    >
                      {showPassword ? (
                        <EyeOff size={16} />
                      ) : (
                        <Eye size={16} />
                      )}
                    </button>
                  </div>
                </label>
              </div>

              <div
                className="row"
                style={{
                  justifyContent: "flex-end",
                }}
              >
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={closeEdit}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={saving}
                >
                  <ShieldCheck size={15} />

                  {saving
                    ? "Saving..."
                    : "Save Changes"}
                </button>
              </div>
            </div>
          </form>
        )}

        {showForm && !showEditForm && (
          <form
            onSubmit={handleCreate}
            className="card"
            style={{ marginBottom: 20 }}
          >
            <div className="stack gap-4">
              <div className="grid grid-cols-2">
                <label className="stack gap-1">
                  <span className="text-small">
                    Username
                  </span>

                  <input
                    className="input"
                    required
                    value={form.username}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        username: e.target.value,
                      })
                    }
                  />
                </label>

                <label className="stack gap-1">
                  <span className="text-small">
                    Full Name
                  </span>

                  <input
                    className="input"
                    required
                    value={form.full_name}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        full_name: e.target.value,
                      })
                    }
                  />
                </label>

                <label className="stack gap-1">
                  <span className="text-small">
                    Password
                  </span>

                  <input
                    className="input"
                    type="password"
                    required
                    value={form.password}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        password: e.target.value,
                      })
                    }
                  />
                </label>

                <label className="stack gap-1">
                  <span className="text-small">
                    Role
                  </span>

                  <select
                    className="input"
                    value={form.role}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        role: e.target.value,
                      })
                    }
                  >
                    {ROLES.map((role) => (
                      <option
                        key={role}
                        value={role}
                      >
                        {role.replace("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div
                className="row"
                style={{
                  justifyContent: "flex-end",
                }}
              >
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setShowForm(false);
                    setForm(emptyForm);
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={saving}
                >
                  <ShieldCheck size={15} />

                  {saving
                    ? "Creating..."
                    : "Create User"}
                </button>
              </div>
            </div>
          </form>
        )}

        {loading ? (
          <Skeleton height={260} />
        ) : users.length === 0 ? (
          <div className="empty-state">
            No users found.
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={users}
          />
        )}
      </Section>
    </div>
  );
}