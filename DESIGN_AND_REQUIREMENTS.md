# News Application: Design and Requirements

## 1. Problem Summary
This application allows readers to consume approved news content published by:
- Independent journalists
- Publishers (with editorial workflows)

The system supports role-based behavior for Reader, Journalist, and Editor users.

## 2. Functional Requirements

### 2.1 User and Access Management
- The system uses a custom user model with a `role` field.
- Supported roles:
  - Reader
  - Journalist
  - Editor
- Each user is automatically assigned to a Django group based on role.
- Group permissions are mapped as follows:
  - Reader: view articles and newsletters only.
  - Editor: view, update, and delete articles/newsletters.
  - Journalist: create, view, update, and delete articles/newsletters.

### 2.2 Publisher Management
- A publisher has:
  - name
  - description
  - created timestamp
- A publisher can be linked to many editors and many journalists.

### 2.3 Article Management
- An article contains:
  - title
  - content
  - author (journalist)
  - created_at
  - approved (boolean)
  - publisher (optional)
- Articles can be:
  - Independent: authored by a journalist without a publisher.
  - Publisher content: linked to a publisher.
- Editors can approve articles.
- Approval triggers:
  - Subscriber notification process
  - API logging to approval endpoint

### 2.4 Newsletter Management
- A newsletter contains:
  - title
  - description
  - created_at
  - author
  - many-to-many relation to articles
- Newsletters can be viewed by readers.
- Newsletters can be created/edited by journalists and editors.

### 2.5 Reader Subscriptions
- Reader users can subscribe to:
  - Publishers (ManyToMany)
  - Journalists (ManyToMany)
- Subscription-based article feed endpoint returns approved content from followed publishers/journalists.

### 2.6 Journalist-Specific Behavior
- Journalist users publish independent content through reverse relations:
  - `articles` on user
  - `newsletters` on user
- If a user role is not Reader, reader subscription fields are cleared to satisfy role-specific field behavior.

## 3. Non-Functional Requirements
- Security:
  - Authentication required for protected endpoints.
  - Role/group authorization for create/update/delete/approve actions.
- Data integrity:
  - Model validation enforces business rules.
  - Group-permission mapping is deterministic.
- Maintainability:
  - Separation of concerns across models, forms, views, serializers, utilities, and signals.
  - Unit tests for role access, API behavior, and approval workflow.
- Reliability:
  - Approval side-effects (notifications/logging) are isolated in signals and utility functions.
- Performance:
  - Use of `select_related` and filtered querysets in views and API endpoints.

## 4. UI/UX Front-End Plan

### 4.1 Navigation and Information Architecture
- Top-level navigation:
  - Home
  - Articles
  - Newsletters
  - Publishers
  - Subscriptions (Reader only)
  - Pending Articles (Editor only)
- Role-based actions appear conditionally to reduce clutter.

### 4.2 Reader Experience
- Home page prioritizes approved articles and latest newsletters.
- Article detail clearly indicates publisher/source and publication state.
- Subscription management uses checkbox lists for journalists and publishers.

### 4.3 Journalist Experience
- Guided article creation form with optional publisher selection.
- Clear messaging that new/edited content may require editorial approval.

### 4.4 Editor Experience
- Dedicated pending article queue.
- One-click approval flow with explicit confirmation page.

### 4.5 UX Quality Principles
- Form validation messages are clear and actionable.
- Permission failures return user-friendly flash messages.
- Interfaces are responsive and legible on mobile and desktop.
- Keep consistency across buttons, cards, and headings in templates.

## 5. Database Design and Normalization

### 5.1 Core Entities
- CustomUser
- Publisher
- Article
- Newsletter
- ApprovedArticleLog

### 5.2 Relationship Summary
- Publisher ↔ CustomUser (editors): M:N
- Publisher ↔ CustomUser (journalists): M:N
- CustomUser (Reader) ↔ Publisher subscriptions: M:N
- CustomUser (Reader) ↔ CustomUser (Journalist subscriptions): M:N
- CustomUser (Journalist) → Article: 1:N
- CustomUser (Journalist/Editor) → Newsletter: 1:N
- Newsletter ↔ Article: M:N
- Article → Publisher: N:1 (optional)
- ApprovedArticleLog → Article: N:1

### 5.3 Normal Form Review
- 1NF: All attributes are atomic; no repeating groups in a single row.
- 2NF: Non-key attributes depend on the full key (junction tables resolve many-to-many relationships).
- 3NF: Non-key attributes depend only on primary key and not on other non-key attributes.

### 5.4 Why This Design Is Normalized
- Role-based and subscription data is separated from article/newsletter content.
- Many-to-many relations are represented with dedicated intermediate tables by Django.
- Publisher affiliation is separated from article records to avoid data duplication.

## 6. Implementation Notes
- Existing project already includes a Django project/app scaffold.
- Role groups are created/updated after migrations.
- User-to-group mapping is enforced on user save.
- Model-level validation now guards newsletter author role constraints.

## 7. Verification Checklist
- [x] Custom user with roles and role-group assignment
- [x] Publisher model with multiple editors and journalists
- [x] Article model includes required fields and approval workflow
- [x] Newsletter model with many-to-many articles
- [x] Reader subscriptions to publishers and journalists
- [x] Role-based permissions enforced in views/API and groups
- [x] Database normalization documented
- [x] Front-end UX plan documented
