import assert from 'node:assert/strict'
import test from 'node:test'
import { createLatestGuard } from './.build/latest.js'

test('only the latest request may apply its result', () => {
  const guard = createLatestGuard()
  const first = guard.next()
  const second = guard.next()
  assert.equal(guard.isCurrent(first), false)
  assert.equal(guard.isCurrent(second), true)
})

test('older responses are rejected after a newer request starts', () => {
  const guard = createLatestGuard()
  const a = guard.next()
  assert.equal(guard.isCurrent(a), true)
  const b = guard.next()
  assert.equal(guard.isCurrent(a), false)
  assert.equal(guard.isCurrent(b), true)
})
