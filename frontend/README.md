\# frontend/README.md



\# detecktiv.io Frontend



A modern, responsive web interface for the detecktiv.io customer intelligence platform. Built following the VDI brand guidelines with a focus on sophisticated design and professional user experience.



\## 🎯 Features



\- \*\*User Management\*\*: Complete CRUD operations for user accounts

\- \*\*Authentication\*\*: Secure login with JWT token management

\- \*\*Profile Management\*\*: Self-service profile updates

\- \*\*Responsive Design\*\*: Works perfectly on desktop, tablet, and mobile

\- \*\*Modern UI\*\*: Glass morphism effects, smooth animations, professional color scheme

\- \*\*Brand Compliant\*\*: Follows VDI brand guidelines exactly

\- \*\*Accessible\*\*: WCAG 2.1 AA compliant design



\## 🛠 Tech Stack



\- \*\*Frontend Framework\*\*: React 18 with TypeScript

\- \*\*Styling\*\*: Tailwind CSS with custom VDI brand tokens

\- \*\*Routing\*\*: React Router v6

\- \*\*Data Fetching\*\*: TanStack Query (React Query)

\- \*\*Icons\*\*: Heroicons

\- \*\*Build Tool\*\*: Vite

\- \*\*UI Components\*\*: Headless UI (accessible components)



\## 📋 Prerequisites



Before you start, make sure you have:



1\. \*\*Node.js\*\* (version 18 or higher)

&nbsp;  - Download from: https://nodejs.org/

&nbsp;  - Check version: `node --version`



2\. \*\*npm\*\* (comes with Node.js)

&nbsp;  - Check version: `npm --version`



3\. \*\*Backend API running\*\* at `http://localhost:8000`

&nbsp;  - Follow the backend setup instructions first

&nbsp;  - Ensure `docker compose up -d` is running



\## 🚀 Quick Start



\### 1. Install Dependencies



```bash

\# Navigate to the frontend directory

cd frontend



\# Install all required packages

npm install

```



\### 2. Environment Setup



```bash

\# Copy the environment template

cp .env.example .env



\# The default settings should work for local development

\# VITE\_API\_URL=http://localhost:8000

```



\### 3. Start Development Server



```bash

\# Start the development server

npm run dev

```



The application will be available at: \*\*http://localhost:5173\*\*



\## 🔧 Available Commands



```bash

\# Start development server with hot reload

npm run dev



\# Build for production

npm run build



\# Preview production build locally

npm run preview



\# Run linting

npm run lint

```



\## 🌐 Usage Guide



\### First Time Setup



1\. \*\*Backend must be running\*\*: Ensure your Docker containers are up

&nbsp;  ```bash

&nbsp;  # In your backend directory

&nbsp;  docker compose up -d

&nbsp;  ```



2\. \*\*Open the frontend\*\*: Navigate to http://localhost:5173



3\. \*\*Login\*\*: Use the credentials provided by your backend setup



\### Main Features



\#### User Management (Admin)

\- \*\*View Users\*\*: Browse all users with search and pagination

\- \*\*Create Users\*\*: Add new team members with role assignment

\- \*\*Edit Users\*\*: Update user details and permissions  

\- \*\*Deactivate Users\*\*: Safely remove user access



\#### Profile Management

\- \*\*View Profile\*\*: See your account details and history

\- \*\*Edit Name\*\*: Update your display name

\- \*\*Account Info\*\*: View creation date, role, and status



\## 🎨 Brand Guidelines Integration



This frontend implements the VDI brand guidelines completely:



\### Colors

\- \*\*detecktiv Purple\*\* (`#6B46C1`): Primary actions, brand elements

\- \*\*Tech Black\*\* (`#0F172A`): Backgrounds, primary text

\- \*\*Trust Silver\*\* (`#9CA3AF`): Secondary text, borders

\- \*\*Success Green\*\* (`#10B981`): Positive indicators

\- \*\*Alert Orange\*\* (`#F59E0B`): Warnings, opportunities

\- \*\*Critical Red\*\* (`#EF4444`): Errors, urgent actions



\### Typography

\- \*\*Font\*\*: Inter (Google Fonts)

\- \*\*Scales\*\*: Hero (56px), Header (32px), Data (18px), Body (16px)

\- \*\*Weights\*\*: Regular (400), Medium (500), Semibold (600), Bold (700)



\### Components

\- \*\*Glass morphism cards\*\*: Subtle backdrop blur effects

\- \*\*Modern shadows\*\*: Elevated, interactive elements

\- \*\*Smooth animations\*\*: 200-300ms transitions

\- \*\*Professional spacing\*\*: 8px grid system



\## 🔌 API Integration



The frontend communicates with your backend at `http://localhost:8000/v1/\*`



\### Endpoints Used

\- `POST /v1/auth/login` - User authentication

\- `GET /v1/users/me` - Current user profile

\- `GET /v1/users` - List users (with pagination)

\- `POST /v1/users` - Create new user

\- `GET /v1/users/{id}` - Get user details

\- `PATCH /v1/users/{id}` - Update user

\- `DELETE /v1/users/{id}` - Deactivate user



\### Authentication

\- Uses JWT tokens stored in localStorage

\- Automatic token refresh on API calls

\- Redirects to login on 401 errors

\- Secure logout clears all stored data



\## 🛡️ Security Features



\- \*\*Token Management\*\*: Secure storage and automatic cleanup

\- \*\*Input Validation\*\*: Client-side validation for all forms

\- \*\*Error Handling\*\*: Graceful error messages, no sensitive data exposure

\- \*\*Rate Limiting\*\*: Handles 429 responses from backend

\- \*\*CORS\*\*: Properly configured for development and production



\## 📱 Responsive Design



The interface adapts perfectly to all screen sizes:



\- \*\*Desktop\*\* (1024px+): Full sidebar, multi-column layouts

\- \*\*Tablet\*\* (768px-1023px): Collapsible sidebar, responsive grids

\- \*\*Mobile\*\* (320px-767px): Hidden sidebar, stacked layouts, touch-optimized



\## ♿ Accessibility



Built with accessibility in mind:



\- \*\*Keyboard Navigation\*\*: Full tab support

\- \*\*Screen Readers\*\*: Proper ARIA labels and semantic HTML

\- \*\*Color Contrast\*\*: WCAG AA compliant contrast ratios

\- \*\*Focus Indicators\*\*: Clear focus rings on all interactive elements



\## 🚨 Troubleshooting



\### Common Issues



\*\*1. "Cannot connect to API"\*\*

\- Check backend is running: `docker compose ps`

\- Verify API URL in `.env` file

\- Check browser console for CORS errors



\*\*2. "Login failed"\*\*

\- Ensure backend auth endpoint is working

\- Check credentials are valid

\- Verify token storage in browser dev tools



\*\*3. "Build fails"\*\*

\- Clear node\_modules: `rm -rf node\_modules \&\& npm install`

\- Check Node.js version: `node --version` (should be 18+)

\- Verify all TypeScript errors are resolved



\*\*4. "Styles not loading"\*\*

\- Ensure Tailwind is configured: `npx tailwindcss --version`

\- Check PostCSS config is present

\- Verify CSS imports in main.tsx



\### Development Tips



1\. \*\*Hot Reload\*\*: Changes save automatically in development

2\. \*\*DevTools\*\*: Use React DevTools browser extension

3\. \*\*Network Tab\*\*: Monitor API calls in browser dev tools

4\. \*\*Console\*\*: Check for JavaScript errors regularly



\## 📦 Deployment



\### Production Build



```bash

\# Create optimized production build

npm run build



\# Files will be in the 'dist' directory

\# Deploy the 'dist' folder to your web server

```



\### Environment Variables for Production



```bash

\# Update .env for production

VITE\_API\_URL=https://your-api-domain.com

VITE\_ENV=production

```



\### Deployment Options



\- \*\*Vercel\*\*: Connect GitHub repo for automatic deployments

\- \*\*Netlify\*\*: Drag and drop the `dist` folder

\- \*\*Traditional Hosting\*\*: Upload `dist` folder contents

\- \*\*CDN\*\*: Use with CloudFront or similar for global delivery



\## 🤝 Development Workflow



\### Making Changes



1\. \*\*Create Feature Branch\*\*: `git checkout -b feature/new-feature`

2\. \*\*Make Changes\*\*: Edit files, test locally

3\. \*\*Test\*\*: Verify all functionality works

4\. \*\*Commit\*\*: `git commit -m "Add new feature"`

5\. \*\*Push\*\*: `git push origin feature/new-feature`



\### Code Standards



\- \*\*TypeScript\*\*: All files use TypeScript for type safety

\- \*\*ESLint\*\*: Follow the configured linting rules

\- \*\*Imports\*\*: Use absolute imports with `@/` prefix

\- \*\*Components\*\*: One component per file, PascalCase names

\- \*\*API\*\*: All API calls use the centralized client



\## 📞 Support



For technical support or questions:



1\. \*\*Check this README\*\* for common solutions

2\. \*\*Review browser console\*\* for error messages

3\. \*\*Verify backend logs\*\* for API issues

4\. \*\*Check network tab\*\* for failed requests



\## 🎉 You're Ready!



Your detecktiv.io frontend is now set up and ready to use. The interface provides a sophisticated, brand-compliant experience for managing your customer intelligence platform.



Key URLs to bookmark:

\- \*\*Frontend\*\*: http://localhost:5173

\- \*\*Backend API\*\*: http://localhost:8000

\- \*\*API Docs\*\*: http://localhost:8000/docs

