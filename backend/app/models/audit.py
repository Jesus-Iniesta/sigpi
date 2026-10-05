"""Backward-compatible exports for the audit model."""

from app.models.auditoria import AuditLog, Auditoria

__all__ = ["AuditLog", "Auditoria"]
