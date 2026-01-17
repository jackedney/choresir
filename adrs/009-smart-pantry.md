ADR 009: Smart Pantry & Grocery Management System

Status: Accepted
Date: 2026-01-17
Deciders: Product Owner, Development Team
Technical Context: Household members struggled with inventory management and shopping list coordination, leading to duplicate purchases, missed items, and inefficient shopping trips. Users needed a natural way to track pantry items and maintain a shared grocery list through conversational WhatsApp interactions.

Decision: We will implement a Smart Pantry module that tracks household inventory status and maintains a shared grocery list, integrated with the existing Choresir agent through specialized tools and services.

## Architecture

### Domain Layer

**New Domain Models** (`src/domain/pantry.py`):
- `PantryItem`: Represents inventory items with status tracking (IN_STOCK, LOW, OUT)
- `ShoppingListItem`: Represents items needed for purchase
- `PantryItemStatus`: Enum for inventory status states

**Design Rationale:**
- Pydantic models ensure type safety and validation
- DTOs decouple database representation from business logic
- Simple status enum provides clear inventory state without complexity

### Data Schema

**New PocketBase Collections** (`src/core/schema.py`):

**pantry_items:**
- `name` (text, required, unique): Normalized item name
- `quantity` (number, optional): Current stock quantity
- `status` (select, required): One of IN_STOCK, LOW, OUT
- `last_restocked` (date, optional): Timestamp of last restocking

**shopping_list:**
- `item_name` (text, required): Item to purchase
- `added_by` (relation to users, required): User who added item
- `added_at` (date, required): When item was added
- `quantity` (number, optional): How many to buy
- `notes` (text, optional): Additional preferences (e.g., "organic only")

**Access Control Decisions:**

*pantry_items:*
- List/View/Create/Update: Open to all users (empty rules)
- Delete: Admin-only (null rule)
- **Rationale:** Prevents accidental inventory data loss while allowing normal updates. Service layer uses admin auth for intentional deletions.

*shopping_list:*
- All operations: Open to all users
- **Rationale:** Shopping list items are transient by nature. Users should freely add/remove items as needs change.

**Index Strategy:**
- `pantry_items`: Unique index on `name` to prevent duplicate inventory entries
- `shopping_list`: No unique constraints (allows tracking item re-additions for UX feedback)

### Service Layer

**New Service** (`src/services/pantry_service.py`):

Key functions with architectural decisions:

**`add_to_shopping_list()`:**
- **Accumulative Quantity:** When adding an existing item, quantities are summed rather than replaced
- **Rationale:** Supports natural household behavior where multiple people might independently request the same item ("we need 2 milks" + "get 3 more milks" = 5 total)
- **Case-Insensitive Matching:** Uses PocketBase's `~` operator for database-level case-insensitive lookups
- **Trade-off:** Requires explicit removal+re-add to replace quantities, but provides better UX for the common case

**`checkout_shopping_list()`:**
- **Non-Atomic Operation:** Explicitly documented as not being a transaction
- **Rationale:** PocketBase (SQLite) doesn't provide distributed transaction support for our use case
- **Error Handling:** Logs exactly which items were processed if failure occurs midway
- **Recovery Strategy:** Users retry checkout on failure (idempotent by design)
- **Consequence:** Accepts risk of inconsistent state on partial failure in exchange for implementation simplicity

**`_update_pantry_item()`:**
- **Private Helper:** Internal-only function for pantry updates during checkout
- **Quantity Accumulation:** Adds incoming quantity to existing stock
- **Rationale:** Supports multiple shopping trips without overwriting previous stock

**Case-Insensitive Strategy:**
- All item lookups use PocketBase's `~` operator for database-level matching
- **Rationale:** Delegates case handling to database rather than Python string operations
- **Benefit:** Consistent behavior, simpler code, leverages database indexes
- **Trade-off:** Couples to PocketBase query syntax (acceptable given existing stack commitment)

### Agent Integration

**New Tools Module** (`src/agents/tools/pantry_tools.py`):

Implements six Pydantic AI tools attached to the Choresir agent:

1. `tool_add_to_shopping_list`: Add items to shared list
2. `tool_get_shopping_list`: Retrieve current shopping list
3. `tool_checkout_shopping_list`: Complete shopping trip
4. `tool_remove_from_shopping_list`: Remove specific items
5. `tool_mark_item_out`: Update pantry status and optionally add to list
6. `tool_get_pantry_status`: Check low/out-of-stock items

**Tool Design Decisions:**

*Pydantic Parameter Models:*
- `AddToShoppingList`, `RemoveFromShoppingList`, `MarkItemStatus`
- **Rationale:** Provides strong typing for agent tool calls, automatic validation, better LLM guidance

*Dual-Purpose Status Tool:*
- `tool_mark_item_out` handles both LOW and OUT status with optional shopping list addition
- **Rationale:** Simplifies agent decision-making by combining related actions
- **Alternative Rejected:** Separate tools for LOW vs OUT created unnecessary complexity

*Rich User Feedback:*
- Tools return detailed messages (e.g., "Added 2 more 'milk' to shopping list (now x5 total)")
- **Rationale:** Provides transparency about system state changes, especially important for quantity accumulation behavior
- **Implementation:** Tools check existing state before operations to generate accurate feedback

*Error Handling Pattern:*
- All tools catch exceptions, log with logfire, return user-friendly error messages
- **Rationale:** Prevents agent crashes, maintains conversational flow even on failures

### Testing Strategy

**Comprehensive Unit Tests** (`tests/unit/test_pantry_service.py`):

Coverage includes:
- Basic CRUD operations
- Quantity accumulation logic
- Case-insensitive matching
- Checkout workflow
- Edge cases (empty lists, duplicate items, missing items)

**Test Infrastructure:**
- Uses existing `InMemoryDBClient` fixture for isolated testing
- Monkeypatches `src.core.db_client` functions
- **Benefit:** No database dependencies, fast test execution

## Consequences

### Positive

**User Experience:**
- Natural conversational interface for inventory management
- Automatic quantity tracking prevents over/under-buying
- Shared list visible to all household members
- Flexible note-taking for item preferences

**Development:**
- Clean separation of concerns (domain/service/tools)
- Reuses existing infrastructure (PocketBase, agent framework)
- Comprehensive test coverage from initial implementation
- Extensible design for future enhancements

**Operations:**
- Minimal performance impact (simple CRUD operations)
- Leverages existing observability (logfire spans)
- No new deployment dependencies

### Negative

**Data Consistency:**
- `checkout_shopping_list` is not atomic - partial failures possible
- **Mitigation:** Error logging provides recovery information, retry mechanism available

**Quantity Model Limitations:**
- Accumulative behavior requires user understanding
- No automatic unit conversion (e.g., "2 gallons" vs "1 gallon")
- **Future Enhancement:** Could add smarter quantity parsing/normalization

**Concurrency Edge Cases:**
- Two users adding same item simultaneously might create duplicates (rare due to unique constraints and timing)
- **Acceptable Risk:** Household scale (1-8 users) makes collision unlikely

### Future Enhancements (Not Implemented)

The following were considered but deferred:

**Predictive Restocking:**
- AI-based predictions of when items will run out
- **Deferred:** Requires usage pattern tracking and historical data
- **Reference:** Original feature request mentioned as "Future/AI enhancement"

**Barcode Scanning:**
- Mobile app integration for quick item addition
- **Deferred:** Requires client-side development beyond WhatsApp

**Expiration Tracking:**
- Track best-by dates for perishables
- **Deferred:** Adds schema complexity without immediate user need

**Store Location Integration:**
- Organize list by store aisles or departments
- **Deferred:** Requires store-specific configuration and maintenance

## Migration Path

No database migration required for existing users:
- New collections created via schema initialization script
- Existing collections and data unaffected
- Zero downtime deployment possible

## Documentation

**In-Code Documentation:**
- Comprehensive docstrings on all service functions
- Detailed parameter descriptions on tool models
- Inline comments for non-obvious business logic

**Behavior Specifications:**
- Quantity accumulation behavior documented in both service and tool docstrings
- Case-insensitive matching documented at implementation points
- Non-atomic checkout behavior explicitly called out with recovery strategy

## Alternatives Considered

**Single Collection Approach:**
- Combine pantry_items and shopping_list into one collection with status field
- **Rejected:** Conflates two distinct concepts (inventory vs needs), complicates queries and access control

**Transactional Checkout:**
- Implement two-phase commit for checkout operation
- **Rejected:** Over-engineering for household scale, SQLite limitations, complexity not justified by risk

**Quantity Replacement (Instead of Accumulation):**
- Make `add_to_shopping_list` replace quantity rather than add
- **Rejected:** Less intuitive for household users, creates confusion when multiple people add items

**Separate Agent for Pantry:**
- Create dedicated pantry_agent instead of extending choresir_agent
- **Rejected:** Unnecessary complexity, choresir already handles household management, users expect unified interface

## Alignment with Existing Architecture

This implementation follows established patterns from ADR-001, ADR-002, and ADR-006:

**Stack Consistency:**
- Uses Python/FastAPI/PocketBase as specified in ADR-001
- Pydantic models align with existing validation strategy
- Logfire spans for observability

**Agent Integration:**
- Follows Pydantic AI tool pattern from ADR-002
- Maintains single-agent-per-domain principle
- Uses established Deps pattern for context injection

**Code Standards:**
- Adheres to ADR-006 docstring requirements
- Type hints throughout
- Descriptive variable names
- Test coverage for new functionality

## Success Metrics

The implementation successfully enables:
- Users can add items via natural language ("we need eggs")
- Users can retrieve shopping list at store ("I'm at the store")
- Users can complete shopping trip ("I bought the list")
- Multiple users can collaborate on shared list
- Quantity preferences are tracked and accumulated
- Pantry status can be monitored ("what's running low?")

All core user stories from original feature request are satisfied.
