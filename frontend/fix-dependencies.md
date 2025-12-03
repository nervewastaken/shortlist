# Fixing Dependency Issues

If you encounter module resolution errors, follow these steps:

1. **Delete node_modules and package-lock.json:**
   ```bash
   cd frontend
   rm -rf node_modules package-lock.json
   ```
   On Windows PowerShell:
   ```powershell
   cd frontend
   Remove-Item -Recurse -Force node_modules, package-lock.json
   ```

2. **Clear npm cache (optional but recommended):**
   ```bash
   npm cache clean --force
   ```

3. **Reinstall dependencies:**
   ```bash
   npm install
   ```

4. **If issues persist, try installing ajv explicitly:**
   ```bash
   npm install ajv@^8.12.0 --save
   ```

