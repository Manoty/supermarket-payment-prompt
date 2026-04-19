// frontend/src/hooks/usePayment.js

import { useState, useRef } from 'react'
import axiosInstance from '../api/axiosInstance'

const POLL_INTERVAL = 3000   // poll every 3 seconds
const MAX_POLLS = 40         // stop after 40 polls (2 minutes)
const TERMINAL_STATUSES = ['SUCCESS', 'FAILED', 'CANCELLED', 'TIMEOUT']

export function usePayment() {
  const [state, setState] = useState({
    status: 'idle',           // idle | loading | pending | success | failed | error
    transactionId: null,
    transaction: null,
    errorMessage: '',
  })

  const pollRef = useRef(null)
  const pollCount = useRef(0)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
      pollCount.current = 0
    }
  }

  const pollStatus = (transactionId) => {
    stopPolling()
    pollCount.current = 0

    pollRef.current = setInterval(async () => {
      pollCount.current += 1

      if (pollCount.current > MAX_POLLS) {
        stopPolling()
        setState(prev => ({
          ...prev,
          status: 'failed',
          errorMessage: 'Payment timed out. Please try again.',
        }))
        return
      }

      try {
        const { data } = await axiosInstance.get(`/payments/status/${transactionId}/`)

        setState(prev => ({ ...prev, transaction: data }))

        if (TERMINAL_STATUSES.includes(data.status)) {
          stopPolling()
          setState(prev => ({
            ...prev,
            status: data.status === 'SUCCESS' ? 'success' : 'failed',
            errorMessage: data.failure_reason || '',
          }))
        }
      } catch (err) {
        console.error('Polling error:', err)
        // Don't stop polling on network error — try again next interval
      }
    }, POLL_INTERVAL)
  }

  const initiatePayment = async (phoneNumber, amount) => {
    setState({
      status: 'loading',
      transactionId: null,
      transaction: null,
      errorMessage: '',
    })

    try {
      const { data } = await axiosInstance.post('/payments/initiate/', {
        phone_number: phoneNumber,
        amount: amount,
      })

      setState(prev => ({
        ...prev,
        status: 'pending',
        transactionId: data.transaction_id,
      }))

      // Start polling for status updates
      pollStatus(data.transaction_id)

    } catch (err) {
      const message =
        err.response?.data?.detail ||
        err.response?.data?.error ||
        'Failed to initiate payment. Please try again.'

      setState({
        status: 'error',
        transactionId: null,
        transaction: null,
        errorMessage: typeof message === 'string' ? message : JSON.stringify(message),
      })
    }
  }

  const reset = () => {
    stopPolling()
    setState({
      status: 'idle',
      transactionId: null,
      transaction: null,
      errorMessage: '',
    })
  }

  return { ...state, initiatePayment, reset }
}