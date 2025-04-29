# Experts Land

A modern, flexible database system with web interface and robust API capabilities.

## Project Structure

```
experts-land/
├── frontend/          # React-based web interface
├── backend/           # FastAPI-based backend service
└── docs/             # Project documentation
```

## Features

- Modern, responsive web interface built with React
- Fast, scalable backend API using FastAPI
- PostgreSQL database with SQLAlchemy ORM
- JWT-based authentication
- Real-time data updates
- Flexible API endpoints
- Role-based access control
- Comprehensive documentation

## Tech Stack

### Frontend
- React 18
- Material-UI
- Redux Toolkit
- Axios
- React Query
- TypeScript

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL
- JWT Authentication
- Pydantic
- Alembic (Database Migrations)

## Getting Started

### Prerequisites
- Node.js 16+
- Python 3.9+
- PostgreSQL 13+
- Docker (optional)

### Installation

1. Clone the repository
2. Set up the backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

3. Set up the frontend:
   ```bash
   cd frontend
   npm install
   ```

4. Configure environment variables:
   - Copy `.env.example` to `.env` in both frontend and backend directories
   - Update the variables according to your setup

5. Start the development servers:
   - Backend: `uvicorn main:app --reload`
   - Frontend: `npm start`

## Development

- Backend API documentation available at `/docs` when running the server
- Frontend development server runs on port 3000
- Backend development server runs on port 8000

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 