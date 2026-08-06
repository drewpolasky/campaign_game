import React from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import Lobby from './screens/Lobby.jsx'
import Play from './screens/Play.jsx'
import './styles.css'

const router = createBrowserRouter([
  { path: '/', element: <Lobby /> },
  { path: '/play/:token', element: <Play /> },
])

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
)
