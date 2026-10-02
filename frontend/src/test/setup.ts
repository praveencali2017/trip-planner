import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom doesn't implement layout APIs; MessageList auto-scrolls with this.
Element.prototype.scrollIntoView = () => {}

afterEach(cleanup)
