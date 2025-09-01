\# frontend/PROJECT\_STRUCTURE.md



\# detecktiv.io Frontend - Complete Project Structure



This document explains every file in your frontend project and what it does.



\## 📁 Root Configuration Files



```

frontend/

├── package.json                 # Project dependencies and scripts

├── vite.config.ts              # Build tool configuration

├── tsconfig.json               # TypeScript main configuration

├── tsconfig.app.json           # TypeScript app-specific settings

├── tsconfig.node.json          # TypeScript Node.js settings

├── tailwind.config.js          # Brand styling configuration

├── postcss.config.js           # CSS processing configuration

├── eslint.config.js            # Code quality rules

├── .env.example                # Environment variables template

├── .gitignore                  # Git ignore rules

├── setup.sh                    # Quick setup script

└── README.md                   # Setup and usage instructions

```



\## 📁 Source Code Structure



```

src/

├── main.tsx                    # React application entry point

├── App.tsx                     # Main application component

├── index.css                   # Global styles and brand tokens

│

├── api/

│   └── client.ts              # API communication layer

│

├── stores/

│   └── authStore.ts           # Authentication state management

│

├── components/

│   └── Layout/

│       └── Layout.tsx         # Main application layout

│

└── pages/

&nbsp;   ├── Auth/

&nbsp;   │   └── Login.tsx          # User login page

&nbsp;   ├── Users/

&nbsp;   │   ├── UsersList.tsx      # User management list

&nbsp;   │   ├── UsersCreate.tsx    # Create new user form

&nbsp;   │   ├── UsersView.tsx      # User details view

&nbsp;   │   └── UsersEdit.tsx      # Edit user form

&nbsp;   └── Me/

&nbsp;       └── Profile.tsx        # User profile management

```



\## 🔧 Configuration Files Explained



\### `package.json`

\- \*\*What it does\*\*: Lists all the libraries your app needs (React, Tailwind, etc.)

\- \*\*Key scripts\*\*: 

&nbsp; - `npm run dev` - starts development server

&nbsp; - `npm run build` - creates production version

&nbsp; - `npm run lint` - checks code quality



\### `vite.config.ts`

\- \*\*What it does\*\*: Configures how your app is built and served

\- \*\*Key features\*\*: Hot reload, proxy to backend API, TypeScript support



\### `tailwind.config.js`

\- \*\*What it does\*\*: Implements your VDI brand guidelines as CSS utilities

\- \*\*Key features\*\*: Custom colors, typography scale, spacing system, animations



\### `tsconfig.json` files

\- \*\*What they do\*\*: Configure TypeScript to catch errors and provide better code completion

\- \*\*Benefits\*\*: Prevents bugs, better development experience



\### `.env.example`

\- \*\*What it does\*\*: Template for environment variables

\- \*\*Usage\*\*: Copy to `.env` and customize for your setup



\## 🎨 Styling System



\### `src/index.css`

\- \*\*Brand Colors\*\*: All VDI colors (detecktiv purple, tech black, etc.)

\- \*\*Typography\*\*: Inter font family with proper weights

\- \*\*Components\*\*: Pre-built UI components (buttons, forms, tables)

\- \*\*Glass morphism\*\*: Modern backdrop blur effects

\- \*\*Accessibility\*\*: Focus rings, proper contrast ratios



\## 🔐 Authentication System



\### `src/stores/authStore.ts`

\- \*\*What it does\*\*: Manages user login state throughout the app

\- \*\*Features\*\*: 

&nbsp; - Secure token storage

&nbsp; - Automatic logout on token expiry

&nbsp; - User profile management

&nbsp; - Persistent sessions



\## 🌐 API Integration



\### `src/api/client.ts`

\- \*\*What it does\*\*: Handles all communication with your backend

\- \*\*Features\*\*:

&nbsp; - Automatic authentication headers

&nbsp; - Error handling for 401, 429, etc.

&nbsp; - Rate limiting support

&nbsp; - Consistent error messages



\### API Endpoints Used:

\- `POST /v1/auth/login` - User sign in

\- `GET /v1/users/me` - Current user profile

\- `GET /v1/users` - List all users (admin)

\- `POST /v1/users` - Create new user (admin)

\- `GET /v1/users/{id}` - Get user details

\- `PATCH /v1/users/{id}` - Update user

\- `DELETE /v1/users/{id}` - Deactivate user (returns 204)



\## 🧩 Components Breakdown



\### `src/components/Layout/Layout.tsx`

\- \*\*Purpose\*\*: Main application shell

\- \*\*Features\*\*:

&nbsp; - Responsive sidebar navigation

&nbsp; - User menu with logout

&nbsp; - Page titles

&nbsp; - Mobile-friendly hamburger menu

&nbsp; - Brand-compliant styling



\### `src/App.tsx`

\- \*\*Purpose\*\*: Routes and authentication logic

\- \*\*Features\*\*:

&nbsp; - Protected routes

&nbsp; - Loading states

&nbsp; - Authentication redirects

&nbsp; - Route definitions



\## 📄 Page Components



\### Authentication

\- \*\*`Login.tsx`\*\*: Professional login form with brand styling, password visibility toggle, error handling



\### User Management (Admin Features)

\- \*\*`UsersList.tsx`\*\*: Paginated table, search functionality, action buttons

\- \*\*`UsersCreate.tsx`\*\*: Form validation, role selection, error handling

\- \*\*`UsersView.tsx`\*\*: Professional user profile display, action buttons

\- \*\*`UsersEdit.tsx`\*\*: Inline editing, status toggles, form validation



\### Profile Management

\- \*\*`Profile.tsx`\*\*: Self-service profile editing, account information, quick actions



\## 🎯 Key Features Implemented



\### Brand Compliance

\- ✅ VDI color palette exactly as specified

\- ✅ Inter typography with proper weights and sizing

\- ✅ Glass morphism effects and modern shadows

\- ✅ Professional spacing (8px grid system)

\- ✅ Sophisticated animations and transitions



\### User Experience

\- ✅ Responsive design (desktop, tablet, mobile)

\- ✅ Loading states and error messages

\- ✅ Form validation with inline errors

\- ✅ Keyboard navigation support

\- ✅ Professional empty states



\### Technical Excellence

\- ✅ TypeScript for type safety

\- ✅ React Query for data management

\- ✅ Secure authentication with JWT

\- ✅ Error boundaries and graceful failures

\- ✅ Performance optimizations



\### Accessibility

\- ✅ WCAG 2.1 AA compliant

\- ✅ Proper focus management

\- ✅ Screen reader support

\- ✅ Color contrast compliance

\- ✅ Keyboard-only navigation



\## 🚀 Getting Started Workflow



1\. \*\*Install\*\*: `npm install` (installs all dependencies)

2\. \*\*Environment\*\*: `cp .env.example .env` (configure API URL)

3\. \*\*Backend\*\*: Ensure `docker compose up -d` is running

4\. \*\*Start\*\*: `npm run dev` (starts development server)

5\. \*\*Open\*\*: Visit http://localhost:5173



\## 🔄 Development Workflow



\### Making Changes

1\. Edit files in `src/` directory

2\. Changes appear instantly (hot reload)

3\. Check browser console for errors

4\. Test on different screen sizes



\### Building for Production

1\. Run `npm run build`

2\. Upload `dist/` folder to your web server

3\. Configure environment variables for production



\## 🎉 What You Have Now



You now have a \*\*complete, production-ready frontend\*\* for detecktiv.io that:



\- \*\*Looks Professional\*\*: Matches your brand guidelines perfectly

\- \*\*Works Everywhere\*\*: Responsive design for all devices

\- \*\*Secure\*\*: Proper authentication and data handling

\- \*\*Accessible\*\*: Meets accessibility standards

\- \*\*Maintainable\*\*: Well-organized, documented code

\- \*\*Performant\*\*: Fast loading, smooth interactions



The frontend handles all user management operations and integrates seamlessly with your backend API. It's ready to use immediately and can be extended with additional features as your platform grows.



\## 🆘 Quick Troubleshooting



\*\*Can't see the app?\*\*

\- Check if `npm run dev` is running without errors

\- Visit http://localhost:5173

\- Check browser console for errors



\*\*API errors?\*\*

\- Ensure backend is running: `docker compose ps`

\- Check `.env` file has correct API URL

\- Verify network requests in browser dev tools



\*\*Styling issues?\*\*

\- Clear browser cache

\- Check if Tailwind compiled correctly

\- Verify all CSS imports are working



This frontend represents a complete, professional implementation of your detecktiv.io platform UI. Every component has been carefully crafted to match your brand guidelines and provide an excellent user experience. 🎯

