"""Domain vocabulary for deterministic intent extraction."""

from __future__ import annotations

PRODUCT_PATTERNS = {
    "crm": ["crm", "sales", "lead", "contact", "pipeline"],
    "marketplace": ["marketplace", "seller", "vendor", "buyer", "listing"],
    "ecommerce": ["store", "shop", "cart", "product", "checkout", "order"],
    "booking": ["booking", "appointment", "reservation", "calendar", "slot"],
    "learning": ["lms", "course", "lesson", "student", "teacher", "quiz"],
    "project_management": ["project", "task", "kanban", "sprint", "milestone"],
    "support_desk": ["support", "ticket", "helpdesk", "agent", "sla"],
    "inventory": ["inventory", "stock", "warehouse", "supplier", "purchase"],
    "analytics": ["analytics", "dashboard", "metric", "report", "insight"],
    "finance": ["invoice", "expense", "budget", "payment", "billing"],
    "healthcare": ["clinic", "doctor", "patient", "medical", "prescription"],
    "hr": ["hr", "employee", "leave", "payroll", "recruiting"],
}

FEATURE_PATTERNS = {
    "auth": ["login", "sign in", "signup", "authentication", "auth"],
    "rbac": ["role", "admin", "permission", "access", "rbac"],
    "dashboard": ["dashboard", "home", "overview", "analytics"],
    "payments": ["payment", "stripe", "checkout", "subscription", "premium", "plan"],
    "premium_gating": ["premium", "paid", "plan", "upgrade", "gating"],
    "analytics": ["analytics", "report", "metrics", "insight"],
    "notifications": ["notification", "email", "alert", "reminder"],
    "search": ["search", "filter", "sort"],
    "audit_log": ["audit", "history", "activity log"],
    "realtime": ["real-time", "realtime", "live"],
    "file_upload": ["upload", "attachment", "file", "document"],
    "comments": ["comment", "thread", "discussion", "message"],
}

ENTITY_PATTERNS = {
    "contacts": ["contact", "contacts", "customer", "customers", "lead", "leads"],
    "companies": ["company", "companies", "account", "accounts"],
    "deals": ["deal", "deals", "opportunity", "pipeline"],
    "users": ["user", "users", "member", "members"],
    "roles": ["role", "roles", "permission", "permissions"],
    "products": ["product", "products", "catalog", "sku"],
    "orders": ["order", "orders", "cart", "checkout"],
    "payments": ["payment", "payments", "invoice", "billing"],
    "subscriptions": ["subscription", "subscriptions", "premium", "plan"],
    "bookings": ["booking", "bookings", "appointment", "reservation"],
    "tasks": ["task", "tasks", "todo", "kanban"],
    "projects": ["project", "projects", "milestone", "sprint"],
    "tickets": ["ticket", "tickets", "support", "issue"],
    "courses": ["course", "courses", "lesson", "lessons"],
    "students": ["student", "students", "learner"],
    "files": ["file", "files", "document", "attachment", "upload"],
    "messages": ["message", "messages", "chat", "comment", "discussion"],
    "reports": ["report", "reports", "analytics", "metric"],
    "inventory_items": ["inventory", "stock", "warehouse", "supplier"],
    "employees": ["employee", "employees", "staff", "payroll"],
    "patients": ["patient", "patients"],
}

ROLE_PATTERNS = {
    "admin": ["admin", "owner", "superuser"],
    "manager": ["manager", "lead", "supervisor"],
    "agent": ["agent", "support"],
    "vendor": ["vendor", "seller"],
    "customer": ["customer", "buyer", "client"],
    "student": ["student", "learner"],
    "teacher": ["teacher", "instructor"],
    "doctor": ["doctor", "physician"],
    "patient": ["patient"],
    "member": ["user", "member", "employee"],
}

DEFAULT_FIELDS = {
    "contacts": ["name:text", "email:email", "phone:text", "status:enum", "owner_id:fk:users"],
    "companies": ["name:text", "website:url", "industry:text", "owner_id:fk:users"],
    "deals": ["title:text", "value:money", "stage:enum", "contact_id:fk:contacts", "owner_id:fk:users"],
    "users": ["name:text", "email:email", "role:enum", "status:enum"],
    "roles": ["name:text", "permissions:json"],
    "products": ["name:text", "description:text", "price:money", "status:enum"],
    "orders": ["order_number:text", "customer_id:fk:users", "total:money", "status:enum"],
    "payments": ["provider:text", "amount:money", "currency:text", "status:enum", "user_id:fk:users"],
    "subscriptions": ["user_id:fk:users", "plan:text", "name:text", "price:money", "features:json", "status:enum", "renews_at:date"],
    "bookings": ["title:text", "customer_id:fk:users", "starts_at:datetime", "status:enum"],
    "tasks": ["title:text", "status:enum", "priority:enum", "assignee_id:fk:users"],
    "projects": ["name:text", "status:enum", "due_date:date", "owner_id:fk:users"],
    "tickets": ["subject:text", "priority:enum", "status:enum", "requester_id:fk:users"],
    "courses": ["title:text", "description:text", "status:enum", "teacher_id:fk:users"],
    "students": ["name:text", "email:email", "status:enum"],
    "files": ["name:text", "url:url", "owner_id:fk:users", "entity_ref:text"],
    "messages": ["body:text", "author_id:fk:users", "entity_ref:text"],
    "reports": ["name:text", "filters:json", "owner_id:fk:users"],
    "inventory_items": ["sku:text", "name:text", "quantity:number", "reorder_level:number"],
    "employees": ["name:text", "email:email", "department:text", "status:enum"],
    "patients": ["name:text", "date_of_birth:date", "status:enum"],
}

CONFLICT_PATTERNS = [
    ("no_login_with_roles", ["no login", "without login"], ["admin", "role", "permission", "premium"]),
    ("free_with_premium", ["free only", "completely free", "no payments"], ["premium", "paid", "subscription", "payments"]),
    ("no_database_with_data", ["no database", "without database"], ["save", "store", "users", "orders", "contacts", "analytics"]),
    ("public_with_private_roles", ["public app", "anonymous only"], ["admin", "manager", "role-based", "rbac"]),
]

VAGUE_TERMS = ["app", "platform", "tool", "system", "website"]
