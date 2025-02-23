## **🔹 Step 1: List of Useful Database Queries**
📌 **Run these SQL commands in pgAdmin or your PostgreSQL terminal.**

### **🔍 Check if Users Exist in Database**
```sql
SELECT * FROM users;
```

### **🔍 Check User Progress (Gym & Food Logs)**
```sql
SELECT * FROM progress WHERE user_id = 123456789;
```

### **🔍 Check All Check-Ins Logged**
```sql
SELECT * FROM checkins ORDER BY timestamp DESC;
```

### **🔍 Check for Duplicate Check-Ins (Image Hash)**
```sql
SELECT user_id, image_hash, COUNT(*) FROM checkins GROUP BY user_id, image_hash HAVING COUNT(*) > 1;
```

### **🔍 Check Personal Records (PRs)**
```sql
SELECT * FROM personal_records WHERE user_id = 123456789;
```

### **🔍 Check Top Users in Leaderboard**
```sql
SELECT username, points FROM users ORDER BY points DESC LIMIT 10;
```

✅ **These queries will help debug and validate database updates!**