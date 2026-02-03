# Async & Concurrency

This page describes async and concurrency patterns in WhatsApp Home Boss.

## Async First

Use `async def` for all routes and services.

## Background Tasks

WhatsApp Webhooks MUST return `200 OK` immediately. Use `FastAPI.BackgroundTasks` for AI processing.
