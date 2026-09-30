/**
 * Frontend TypeScript contracts matching backend API schemas.
 */

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  slug: string;
  description?: string;
}

export interface Task {
  id: string;
  project_id: string;
  organization_id: string;
  title: string;
  description: string | null;
  status: "TODO" | "CLAIMED" | "IN_PROGRESS" | "BLOCKED" | "REVIEW" | "DONE" | "FAILED" | "CANCELLED";
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  assigned_agent_id: string | null;
  assigned_user_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  assigned_agent_id?: string;
  assigned_user_id?: string;
}

export interface Agent {
  id: string;
  organization_id: string;
  project_id: string | null;
  name: string;
  slug: string;
  description: string | null;
  role: string;
  model: string;
  model_provider: string;
  status: string;
  capabilities: string[];
}

export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  role: "OWNER" | "ADMIN" | "MEMBER" | "VIEWER";
  created_at: string;
  user?: {
    id: string;
    username: string;
    email: string;
    role: string;
  };
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  is_active?: boolean;
}

export interface UserProfile {
  id: string;
  external_subject: string;
  email: string;
  username: string;
  display_name?: string | null;
  role: string;
  is_active: boolean;
  organization?: Organization | null;
  token_roles?: string[];
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

