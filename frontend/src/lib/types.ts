// Mirrors the API's camelCase JSON (backend/app/schemas).
export type Role = "EMPLOYEE" | "MANAGER" | "HOD";
export type Status =
  | "PENDING_MANAGER"
  | "PENDING_HOD"
  | "NEEDS_INFO"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED";
export type Route = "MANAGER_ONLY" | "MANAGER_THEN_HOD" | "HOD_ONLY";
export type LeaveType = "ANNUAL" | "SICK" | "CASUAL" | "OTHER";
export type DecisionAction = "APPROVE" | "REJECT" | "REQUEST_INFO";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  isDemo: boolean;
}

export interface Me {
  user: User;
  orgToday: string;
  badges: { pendingApprovals: number; needsInfo: number };
  app: { maxUploadFiles: number; maxUploadMb: number; demoMode: boolean };
}

export interface LeaveSummary {
  id: number;
  employeeId: string;
  employeeName: string;
  fromDate: string;
  toDate: string;
  days: number;
  streak: number;
  leaveType: LeaveType;
  reason: string;
  isExtended: boolean;
  status: Status;
  approverRoute: Route;
  version: number;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface Decision {
  id: number;
  stage: "EMPLOYEE" | "MANAGER" | "HOD";
  action: "SUBMIT" | "APPROVE" | "REJECT" | "REQUEST_INFO" | "RESPOND" | "CANCEL";
  actorName: string;
  actorRole: Role;
  fromStatus: Status | null;
  toStatus: Status;
  comment: string | null;
  createdAt: string;
}

export interface LeaveDocument {
  id: string;
  name: string;
  mime: string;
  sizeBytes: number;
  uploadedBy: string;
  createdAt: string;
}

export interface RecentLeave {
  id: number;
  fromDate: string;
  toDate: string;
  days: number;
  status: Status;
}

export interface LeaveDetail extends LeaveSummary {
  resumeStatus: Status | null;
  decisions: Decision[];
  documents: LeaveDocument[];
  recentLeave: RecentLeave[];
  permissions: {
    canDecide: boolean;
    canRespond: boolean;
    canCancel: boolean;
    waitingFor: "MANAGER" | "HOD" | null;
  };
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface Preview {
  days: number;
  streak: number;
  isExtended: boolean;
  chain: { fromDate: string; toDate: string }[];
  requiresDocuments: boolean;
  approvalChain: string[];
  conflict: RecentLeave | null;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actorId: string | null;
  actorName: string | null;
  actorRole: string | null;
  action: string;
  entityType: string;
  entityId: string | null;
  details: Record<string, unknown>;
  requestId: string | null;
}

export interface AuditPage {
  items: AuditEntry[];
  nextCursor: number | null;
}
