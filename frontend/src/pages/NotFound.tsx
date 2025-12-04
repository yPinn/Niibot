import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex flex-col h-full items-center justify-center">
      <h1 className="text-6xl font-bold mb-4">404</h1>
      <p className="text-xl text-gray-600 mb-8">Page not found</p>
      <Link to="/" className="text-blue-600 hover:text-blue-800 underline">
        Go back to home
      </Link>
    </div>
  )
}
