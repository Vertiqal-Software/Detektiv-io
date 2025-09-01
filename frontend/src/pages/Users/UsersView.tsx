// frontend/src/pages/Users/UsersView.tsx
// User Details page – improved on your base without removing features
// - Corrects API imports to match client exports
// - Uses backend field names (full_name, is_superuser) with safe fallbacks
// - Robust loading/error states, confirmed delete (deactivate) action
// - Consistent Tailwind UI with existing components

import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { users as UsersApi, type User, type HttpError } from "@/api/client";
import {
  ArrowLeftIcon,
  PencilSquareIcon,
  TrashIcon,
  EnvelopeIcon,
  CalendarDaysIcon,
  ShieldCheckIcon,
  UserCircleIcon,
} from "@heroicons/react/24/outline";

export default function UsersView() {
  const { id } = useParams<{ id: string }>();
  const userId = id ? Number(id) : NaN;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error } = useQuery<User, HttpError>({
    queryKey: ["user", userId],
    enabled: Number.isFinite(userId),
    queryFn: () => UsersApi.get(userId),
    staleTime: 30_000,
    retry: (count, err) => (err?.status === 401 ? false : count < 2),
  });

  const removeMutation = useMutation({
    mutationFn: () => UsersApi.remove(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      navigate("/users");
    },
    onError: () => {
      // Non-fatal; UI stays on the same page
    },
  });

  if (!Number.isFinite(userId)) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center max-w-md">
          <UserCircleIcon className="mx-auto h-12 w-12 text-trust-silver mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">Invalid user id</h3>
          <p className="text-trust-silver mb-4">
            The URL is missing a valid user identifier.
          </p>
          <Link to="/users" className="btn-primary">
            Back to Users
          </Link>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-detecktiv-purple mx-auto mb-4"></div>
          <p className="text-trust-silver">Loading user…</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    const msg =
      (error?.details as any)?.message ||
      (error?.details as any)?.detail ||
      error?.message ||
      "Unable to load the user.";
    return (
      <div className="flex items-center justify-center py-12">
        <div className="glass-card p-8 text-center max-w-md">
          <UserCircleIcon className="mx-auto h-12 w-12 text-trust-silver mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">User not found</h3>
          <p className="text-trust-silver mb-4">{String(msg)}</p>
          <Link to="/users" className="btn-primary">
            Back to Users
          </Link>
        </div>
      </div>
    );
  }

  // Safe derived fields (align with backend)
  const safeName = data.full_name || "—";
  const safeEmail = data.email || "—";
  const initials = ((data.full_name?.[0] ?? data.email?.[0] ?? "?") + "").toUpperCase();
  const roleLabel = data.role
    ? data.role.replace("_", " ")
    : data.is_superuser
    ? "Admin"
    : "User";
  const isActive = data.is_active ?? true;

  const createdAt = data.created_at
    ? new Date(data.created_at).toLocaleDateString("en-GB", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "—";
  const updatedAt = data.updated_at
    ? new Date(data.updated_at).toLocaleDateString("en-GB")
    : "—";

  const onDelete = () => {
    const label = (data.full_name && data.full_name.trim()) || data.email || `user #${data.id}`;
    const confirmed = window.confirm(
      `Are you sure you want to deactivate ${label}? This action cannot be undone.`
    );
    if (confirmed) {
      removeMutation.mutate();
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/users"
            className="p-2 text-trust-silver hover:text-white transition-colors duration-200 rounded-medium hover:bg-gray-800"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold text-white">User Details</h1>
            <p className="mt-1 text-sm text-trust-silver">
              View and manage user information
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <Link
            to={`/users/${data.id}/edit`}
            className="btn-secondary inline-flex items-center space-x-2"
          >
            <PencilSquareIcon className="h-4 w-4" />
            <span>Edit</span>
          </Link>
          <button
            onClick={onDelete}
            disabled={removeMutation.isPending}
            className="btn-destructive inline-flex items-center space-x-2 disabled:opacity-50"
          >
            <TrashIcon className="h-4 w-4" />
            <span>{removeMutation.isPending ? "Deactivating..." : "Deactivate"}</span>
          </button>
        </div>
      </div>

      {/* User details card */}
      <div className="glass-card rounded-large overflow-hidden">
        {/* User header */}
        <div className="bg-gradient-primary p-6">
          <div className="flex items-center space-x-4">
            <div className="h-16 w-16 rounded-large bg-white/20 backdrop-blur-glass flex items-center justify-center">
              <span className="text-2xl font-bold text-white">{initials}</span>
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white">{safeName}</h2>
              <p className="text-purple-100">{safeEmail}</p>
              <div className="flex items-center space-x-4 mt-2">
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
                    isActive
                      ? "bg-success-green/20 text-success-green"
                      : "bg-gray-600/20 text-gray-300"
                  }`}
                >
                  {isActive ? "Active" : "Inactive"}
                </span>
                <span className="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-xs font-medium text-white capitalize">
                  {roleLabel}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* User information */}
        <div className="p-6 grid grid-cols-1 gap-6 sm:grid-cols-2">
          {/* Basic Information */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white border-b border-gray-700 pb-2">
              Basic Information
            </h3>

            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <EnvelopeIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Email</p>
                  <p className="text-sm text-trust-silver">{safeEmail}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <UserCircleIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Full Name</p>
                  <p className="text-sm text-trust-silver">{safeName}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <ShieldCheckIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Role</p>
                  <p className="text-sm text-trust-silver capitalize">{roleLabel}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Account Information */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white border-b border-gray-700 pb-2">
              Account Information
            </h3>

            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <CalendarDaysIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Created</p>
                  <p className="text-sm text-trust-silver">{createdAt}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <CalendarDaysIcon className="h-5 w-5 text-detecktiv-purple mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Last Updated</p>
                  <p className="text-sm text-trust-silver">{updatedAt}</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="h-5 w-5 flex items-center justify-center mt-0.5">
                  <div
                    className={`h-3 w-3 rounded-full ${
                      isActive ? "bg-success-green" : "bg-gray-500"
                    }`}
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-white">Status</p>
                  <p className="text-sm text-trust-silver">
                    {isActive
                      ? "Active user with full access"
                      : "Inactive - access suspended"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Action section */}
        <div className="border-t border-gray-700 bg-gray-800/30 px-6 py-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-trust-silver">User ID: {data.id}</p>
            <div className="flex items-center space-x-3">
              <Link to={`/users/${data.id}/edit`} className="btn-secondary">
                Edit User
              </Link>
              <button
                onClick={onDelete}
                disabled={removeMutation.isPending}
                className="btn-destructive disabled:opacity-50"
              >
                {removeMutation.isPending ? "Deactivating..." : "Deactivate"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
