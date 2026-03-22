# SATARK Counselling App - Future Plans

## 1. Training Centre Portal (New Page)

A dedicated portal for training centres with:
- Course calendar planning
- Trainee data management
- Link to SATARK Counselling app
- Other training-related modules

### User Flow
- Training centre users login → redirected to Training Centre Portal
- From there, they access SATARK and other training modules
- Back button returns to Training Centre Portal

## 2. Authentication Options (To Be Implemented)

### Option A: CMS ID Based Login (Standalone)
- SATARK app has its own login page
- User enters CMS ID
- Validates against `div_cli_master` or `div_staff_master`
- Restricts to CLIs/Instructors only

### Option B: Integrated with bbtro Roles
- Training centre users have special role in bbtro
- Login at `crtms.in` → redirected based on role:
  - `division` role → Division Dashboard (`/div/`)
  - `training_centre` role → Training Centre Portal (new page)
- Sidebar shows only relevant links per role

### Option C: bbtro Session Validation (Like RTIS)
- Check `connect.sid` cookie from bbtro
- Validate session against MySQL sessions table
- Add `can_access_counselling` flag to users table

## 3. Navigation

### Current State (Deployment)
- App accessible at: `https://crtms.in/counselling/ui/`
- No authentication required
- Link added in bbtro sidebar: "SATARK Counselling"

### Future State
- Training centre users → Training Centre Portal → SATARK
- Division users → Division Dashboard → SATARK (sidebar link)
- Back button behavior handled naturally through portal navigation

## 4. Database Considerations

### For Training Centre Portal
```sql
-- New table for training centre users (if needed)
CREATE TABLE div_training_centre_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cms_id VARCHAR(15) NOT NULL UNIQUE,
    name VARCHAR(100),
    centre_code VARCHAR(20),
    active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Or add role column to existing users table
ALTER TABLE users ADD COLUMN role ENUM('division', 'training_centre', 'admin') DEFAULT 'division';
```

## 5. Implementation Priority

1. ✅ Deploy SATARK app (current)
2. 🔲 Create Training Centre Portal page
3. 🔲 Add role-based routing in bbtro
4. 🔲 Implement CMS ID login for SATARK (optional)
